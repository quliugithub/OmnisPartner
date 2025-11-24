
"""Repository helpers for deploy file management."""

from __future__ import annotations

import pymysql
from contextlib import contextmanager
from typing import Dict, Iterable, Sequence, Tuple, List, Optional

from app.db import mysql_connection
from app.modules.deployfilemanage.domain import (
    DeployTaskListEntry,
    DeployConfDiffDetailRecord,
    DeployReplaceWarRecord,
    DepServerInfo,
)
from app.settings import Settings


class DepRepRepository:
    """Subset of DepRepDBOperator required for file replacement."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def _conn(self):
        conn = mysql_connection(self.settings)
        try:
            yield conn
        finally:
            conn.close()

    def get_global_details(self, hospital_code: str, env_name: str, group_name: str) -> Dict[str, str]:
        sql = (
            "SELECT DISTINCT param_key, param_value "
            "FROM global_conf_details "
            "WHERE global_group_id IN ("
            "    SELECT a.global_group_id "
            "    FROM global_conf_group a "
            "    JOIN server_env c ON a.server_env_id = c.server_env_id "
            "    WHERE c.hospital_code = %s "
            "      AND c.server_env_name = %s "
            "      AND a.global_group_name = %s"
            ")"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (hospital_code, env_name, group_name))
            rows = cur.fetchall()
        return {row["param_key"]: row["param_value"] for row in rows}

    def get_global_conf_group(self, global_group_id: str) -> Tuple[str, Dict[str, str]]:
        """Return the global group name and its key/value pairs."""
        group_sql = "SELECT global_group_name FROM global_conf_group WHERE global_group_id = %s"
        detail_sql = (
            "SELECT param_key, param_value "
            "FROM global_conf_details "
            "WHERE global_group_id = %s"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(group_sql, (global_group_id,))
            group = cur.fetchone()
            if not group:
                raise ValueError(f"Global group {global_group_id} not found")
            cur.execute(detail_sql, (global_group_id,))
            details_rows = cur.fetchall()
        details = {row["param_key"].strip(): row["param_value"] for row in details_rows}
        return group["global_group_name"], details

    def query_task_once_ids(self, dep_event_id: str, task_ids: Iterable[str]) -> Dict[str, str]:
        """Return dep_task_once_id for every task id involved in this event."""
        cleaned = [task_id for task_id in task_ids if task_id]
        if not cleaned:
            return {}
        placeholders = ",".join(["%s"] * len(cleaned))
        sql = (
            "SELECT dep_task_id, dep_task_once_id "
            "FROM deploy_task_once_flow "
            "WHERE dep_event_id = %s "
            f"AND dep_task_id IN ({placeholders})"
        )
        params = [dep_event_id, *cleaned]
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {row["dep_task_id"]: row["dep_task_once_id"] for row in rows}

    def add_deploy_replace_war(self, records: Sequence[DeployReplaceWarRecord]) -> None:
        if not records:
            return
        sql = (
            "INSERT INTO deploy_replace_war "
            "(rep_war_id, dep_event_id, dep_rep_id, global_param_id, war_artifactid, "
            " war_groupid, war_version, war_rep_location, create_time, modify_time, comments) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW(),%s)"
        )
        params = [
            (
                record.rep_war_id,
                record.dep_event_id,
                record.dep_rep_id,
                record.global_param_id,
                record.war_artifactid,
                record.war_groupid,
                record.war_version,
                record.war_rep_location,
                record.comments,
            )
            for record in records
        ]
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(sql, params)
            conn.commit()

    def add_deploy_conf_diff_detail(self, records: Sequence[DeployConfDiffDetailRecord]) -> None:
        if not records:
            return
        sql = (
            "INSERT INTO deploy_conf_diff_detail "
            "(diff_id, rep_war_id, param_key, param_org_value, param_rep_value, not_replace, "
            " create_time, modify_time, comments) "
            "VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW(),%s)"
        )
        params = [
            (
                record.diff_id,
                record.rep_war_id,
                record.param_key,
                record.param_org_value,
                record.param_rep_value,
                record.not_replace,
                record.comments,
            )
            for record in records
        ]
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(sql, params)
            conn.commit()

    def get_sys_params(self, names: Sequence[str]) -> Dict[str, str]:
        if not names:
            return {}
        placeholders = ",".join(["%s"] * len(names))
        sql = (
            "SELECT param_name, param_value "
            "FROM sys_param "
            f"WHERE param_name IN ({placeholders}) "
            "  AND sys_project_id = '-1'"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, list(names))
            rows = cur.fetchall()
        return {row["param_name"]: row["param_value"] for row in rows}

    def update_task_status(self, task_ids: Iterable[str], status: str, comments: str) -> int:
        cleaned = [task_id for task_id in task_ids if task_id]
        if not cleaned:
            return 0
        placeholders = ",".join(["%s"] * len(cleaned))
        sql = (
            f"UPDATE deploy_tasklist SET deploystatu = %s, comments = %s "
            f"WHERE dep_task_id IN ({placeholders})"
        )
        params = [status, comments, *cleaned]
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount

    def update_task_checkwar_status(self, status_map: Dict[str, str]) -> None:
        if not status_map:
            return
        sql = "UPDATE deploy_tasklist SET checkwarstatu=%s WHERE dep_task_id=%s"
        params = [
            (status[:255], task_id)
            for task_id, status in status_map.items()
            if task_id
        ]
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(sql, params)
            conn.commit()

    def get_deploy_tasks(self, task_ids: Iterable[str]) -> Dict[str, DeployTaskListEntry]:
        cleaned = [task_id for task_id in task_ids if task_id]
        if not cleaned:
            return {}
        placeholders = ",".join(["%s"] * len(cleaned))
        sql = f"""
            SELECT a.dep_task_id,a.war_artifactid,a.war_groupid,a.global_group_id,
                   a.deploydir,a.server_id,a.lastversion,a.lastdeployver,
                   a.install_soft_id,a.singledep_bak_path,
                   a.appurl,a.hospital_code,
                   b.server_ip,b.server_port,b.server_os,b.server_env_id,
                   su.soft_home AS soft_home_dir,
                   su.user_name AS os_user_name,
                   su.user_pwd AS os_user_pwd,
                   su.soft_type,su.portoffset,su.service_port,
                   su.install_soft_id,
                   su.portoffset,
                   su.user_name,
                   su.user_pwd
            FROM deploy_tasklist a
            JOIN server_instance b ON a.server_id = b.server_id
            LEFT JOIN (
                SELECT c.*, d.user_name, d.user_pwd
                FROM server_install_soft c
                LEFT JOIN server_os_users d ON c.server_os_user_id = d.server_os_user_id
            ) su ON a.install_soft_id = su.install_soft_id
            WHERE a.dep_task_id IN ({placeholders})
        """
        params = cleaned
        entries: Dict[str, DeployTaskListEntry] = {}
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            entry = DeployTaskListEntry(
                dep_task_id=row["dep_task_id"],
                war_artifactid=row.get("war_artifactid", ""),
                war_groupid=row.get("war_groupid", ""),
                global_id=row.get("global_group_id", ""),
                server_ip=row.get("server_ip", ""),
                deploydir=row.get("deploydir"),
                server_id=row.get("server_id"),
                lastversion=row.get("lastversion"),
                soft_home_dir=row.get("soft_home_dir"),
                os_user_name=row.get("os_user_name"),
                os_user_pwd=row.get("os_user_pwd"),
                appurl=row.get("appurl"),
                hospital_code=row.get("hospital_code"),
                soft_type=row.get("soft_type"),
                portoffset=row.get("portoffset"),
                service_port=row.get("service_port"),
                server_os=row.get("server_os"),
                remote_connect_port=row.get("server_port"),
                install_soft_id=row.get("install_soft_id"),
                lastdeployver=row.get("lastdeployver"),
                singledep_bak_path=row.get("singledep_bak_path"),
            )
            entries[entry.dep_task_id] = entry
        missing = set(cleaned) - set(entries.keys())
        if missing:
            raise ValueError(f"Missing deploy tasks: {', '.join(missing)}")
        return entries

    # ---------------------- SpringBoot helpers --------------------- #
    def get_task_appurl(self, task_id: str) -> Optional[str]:
        sql = "SELECT appurl FROM deploy_tasklist WHERE dep_task_id = %s"
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (task_id,))
            row = cur.fetchone()
        if not row:
            return None
        value = row.get("appurl")
        if value is None or str(value).lower() == "null":
            return None
        return str(value)

    def get_task_springboot_server_port(self, task_id: str) -> Optional[str]:
        sql = (
            "SELECT DISTINCT b.param_value "
            "FROM deploy_tasklist a "
            "JOIN global_conf_details b ON a.global_group_id = b.global_group_id "
            "WHERE b.param_key = 'server.port' AND a.dep_task_id = %s"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (task_id,))
            row = cur.fetchone()
        return str(row["param_value"]) if row and row.get("param_value") is not None else None

    def get_service_port(self, task_id: str) -> Optional[str]:
        sql = (
            "SELECT b.service_port "
            "FROM deploy_tasklist a "
            "INNER JOIN server_install_soft b ON a.install_soft_id = b.install_soft_id "
            "WHERE a.dep_task_id = %s"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (task_id,))
            row = cur.fetchone()
        return str(row["service_port"]) if row and row.get("service_port") is not None else None

    def get_soft_manager_port(self, task_id: str) -> Optional[str]:
        sql = (
            "SELECT b.manage_port "
            "FROM deploy_tasklist a "
            "INNER JOIN server_install_soft b ON a.install_soft_id = b.install_soft_id "
            "WHERE a.dep_task_id = %s"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (task_id,))
            row = cur.fetchone()
        return str(row["manage_port"]) if row and row.get("manage_port") is not None else None

    def get_spingboot_env_conf_text(self, task_id: str) -> Optional[str]:
        sql = "SELECT env_conf FROM deptask_springboot_conf WHERE dep_task_id = %s AND isvalid = '1'"
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (task_id,))
            rows = cur.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(f"{task_id} 存在多条有效 env.conf 记录，请检查数据库")
        value = rows[0].get("env_conf")
        return str(value) if value is not None else None

    def update_task_list_online_version(self, task_id: str, version: str) -> None:
        sql = "UPDATE deploy_tasklist SET publish_req_ver = %s WHERE dep_task_id = %s"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (version, task_id))
            conn.commit()

    def update_task_list_app_url(self, task_id: str, appurl: str) -> None:
        sql = "UPDATE deploy_tasklist SET appurl = %s WHERE dep_task_id = %s"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (appurl, task_id))
            conn.commit()

    def update_task_list_nover_by_task(self, task_id: str, appstatu: str, appurl: str) -> None:
        sql = "UPDATE deploy_tasklist SET appstatu = %s, appurl = %s WHERE dep_task_id = %s"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (appstatu, appurl, task_id))
            conn.commit()

    def update_task_list_by_task(
        self,
        task_id: str,
        appstatu: str,
        appurl: str,
        publish_req_ver: str,
        framework_version: Optional[str],
    ) -> None:
        sql = (
            "UPDATE deploy_tasklist "
            "SET appstatu = %s, appurl = %s, publish_req_ver = %s, framework_version = %s "
            "WHERE dep_task_id = %s"
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (appstatu, appurl, publish_req_ver, framework_version, task_id))
            conn.commit()
