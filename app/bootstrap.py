"""Bootstrap logic that mirrors `OmnisPartnerApplication.run`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .license import Lic4Business, OmnisProductName
from .services import (
    AfterServerStartInit,
    AlertInfoCache,
    AlertManagerService,
    CbhReportService,
    DbEventOperatorService,
    DeployInfoRefresh,
    DeployInvoker,
    EsbAgentService,
    FineReportService,
    RecoveryService,
    SysService,
)
from app.modules.alertmanager.cache.loader import load_cache_from_mysql
from app.modules.alertmanager.cache import AlertInfoCache as AlertInfoCacheEngine
from app.modules.alertmanager.repositories.mysql import MySQLAlertManagerRepository
from app.modules.deployfilemanage import DeployFileManageService
from app.modules.deployfilemanage.repositories import DepRepRepository
from app.modules.deployfilemanage.service.deploy_process import DeployProcessService
from app.modules.deployfilemanage.deploy import (
    DeployInvokerService,
    JbossCliExecutor,
    SpringBootDeployer,
)
from .settings import Settings
from .switches import OmnisSwitch

log = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    """Container that wires plain-Python services with shared settings."""

    settings: Settings
    sys_service: SysService = field(init=False)
    after_server_start_init: AfterServerStartInit = field(init=False)
    deploy_invoker: DeployInvoker = field(init=False)
    deploy_info_refresh: DeployInfoRefresh = field(init=False)
    alert_info_cache: AlertInfoCache = field(init=False)
    alert_manager_service: AlertManagerService = field(init=False)
    esb_agent_service: EsbAgentService = field(init=False)
    fine_report_service: FineReportService = field(init=False)
    cbh_report_service: CbhReportService = field(init=False)
    recovery_service: RecoveryService = field(init=False)
    db_event_operator_service: DbEventOperatorService = field(init=False)
    deployfile_service: DeployFileManageService = field(init=False)
    dep_rep_repository: DepRepRepository = field(init=False)
    deploy_process_service: DeployProcessService = field(init=False)
    deploy_thread_manager: DeployInvokerService = field(init=False)

    def __post_init__(self) -> None:
        self.sys_service = SysService(self.settings)
        self.after_server_start_init = AfterServerStartInit(self.settings)
        self.deploy_invoker = DeployInvoker(self.settings)
        self.deploy_info_refresh = DeployInfoRefresh(self.settings)
        self.alert_repository = MySQLAlertManagerRepository(self.settings)
        try:
            cache_engine = load_cache_from_mysql(self.alert_repository)
        except Exception as exc:  # noqa: BLE001
            log.warning("Falling back to sample AlertManager cache: %s", exc)
            cache_engine = AlertInfoCacheEngine.from_sample()

        self.alert_info_cache = AlertInfoCache(self.settings, cache_engine=cache_engine)
        self.alert_manager_service = AlertManagerService(
            self.settings,
            alert_cache=self.alert_info_cache,
            repository=self.alert_repository,
        )
        self.esb_agent_service = EsbAgentService(self.settings)
        self.fine_report_service = FineReportService(self.settings)
        self.cbh_report_service = CbhReportService(self.settings)
        self.recovery_service = RecoveryService(self.settings)
        self.db_event_operator_service = DbEventOperatorService(self.settings)
        self.dep_rep_repository = DepRepRepository(self.settings)
        self.deploy_process_service = DeployProcessService(self.dep_rep_repository)
        self.deploy_process_service.init_sys_params()
        cli_executor = JbossCliExecutor(self.deploy_process_service.sys_params)
        springboot_executor = SpringBootDeployer(
            notifier=self.deploy_process_service.notifier,
            repository=self.dep_rep_repository,
            sys_params=self.deploy_process_service.sys_params,
        )
        self.deploy_thread_manager = DeployInvokerService(
            cli_executor=cli_executor,
            status_notifier=self.deploy_process_service.notifier,
            springboot_executor=springboot_executor,
        )
        self.deployfile_service = DeployFileManageService(
            self.settings,
            dep_rep_repo=self.dep_rep_repository,
            deploy_process_service=self.deploy_process_service,
            deploy_invoker=self.deploy_thread_manager,
        )


async def bootstrap_services(container: ServiceContainer, switches: OmnisSwitch) -> None:
    """Invoke the translated startup flow."""

    log.info("...................RUN...................")
    log.info(
        "########### websql=%s alertmanager=%s deploy=%s esbagent=%s ############",
        switches.websql_on(),
        switches.alert_manager_on(),
        switches.deploy_on(),
        switches.esb_agent_on(),
    )

    await container.after_server_start_init.do_init()

    if switches.websql_on():
        log.info("...................RUN-WEBSQL-BEGIN...................")
        if Lic4Business.have_license(OmnisProductName.WEBSQL):
            await container.sys_service.register_myself(container.settings.version)
            await container.sys_service.register_to_center()
            await container.after_server_start_init.do_init_websql()
        else:
            log.error("####################### websql license invalid")
        log.info("...................RUN-WEBSQL-END...................")
    else:
        log.info("websql switch is OFF, skip websql init")


    if switches.alert_manager_on():
        await container.alert_info_cache.init_all()
        log.info("...................RUN-ALERTMANAGER-BEGIN...................")
        if Lic4Business.have_license(OmnisProductName.MONITOR):
            await container.alert_manager_service.interval_msg_send_task()
            await container.alert_manager_service.sync_data_to_remote_thread_invoker()
            await container.alert_manager_service.repeated_alert_msg_auto_confirm()
        else:
            log.error("####################### monitor license invalid")
        log.info("...................RUN-ALERTMANAGER-END...................")
    else:
        log.info("alertmanager switch is OFF, skip alert tasks")

    if switches.deploy_on():
        log.info("...................RUN-DEPLOY-BEGIN...................")
        if Lic4Business.have_license(OmnisProductName.ALL):
            await container.deploy_invoker.invoke()
            await container.deploy_info_refresh.do_refresh_auto()
        else:
            log.error("####################### deploy license invalid")
        log.info("...................RUN-DEPLOY-END...................")
    else:
        log.info("deploy switch is OFF, skip deploy tasks")

    if switches.esb_agent_on():
        log.info("...................RUN-ESB-BEGIN...................")
        await container.esb_agent_service.do_data_sync()
        await container.esb_agent_service.do_ens_messageheader_hour_init()
        log.info("...................RUN-ESB-END...................")

    if switches.finereport_on():
        log.info("...................RUN-REPORT-BEGIN...................")
        await container.fine_report_service.do_data_sync()
        log.info("...................RUN-REPORT-END...................")

    if switches.alert_recovery_on():
        log.info("...................MONITOR-RECOVERY-BEGIN...................")
        if Lic4Business.have_license(OmnisProductName.MONITOR):
            await container.recovery_service.init()
        else:
            log.error("####################### monitor license invalid")
        log.info("...................MONITOR-RECOVERY-END...................")

    if switches.cbh_report_on():
        log.info("...................RUN-CBH-REPORT-BEGIN...................")
        await container.cbh_report_service.init_sys_params()
        await container.cbh_report_service.collect_data_to_db()
        log.info("...................RUN-CBH-REPORT-END...................")

    if switches.deploy_on():
        await container.db_event_operator_service.add_event_to_project_queue_from_db()
        await container.db_event_operator_service.auto_do_url_proxy_event()
    else:
        log.info("deploy switch is OFF, skip db event operator init")
