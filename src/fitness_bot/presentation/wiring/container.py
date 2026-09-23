from __future__ import annotations

import cqrs
from cqrs.container.dependency_injector import DependencyInjectorCQRSContainer
from dependency_injector import containers, providers

from fitness_bot.infrastructure.adapters.exercise_catalog import SqlAlchemyExerciseCatalog
from fitness_bot.infrastructure.adapters.language_model import StubLanguageModel, TimewebLanguageModel
from fitness_bot.infrastructure.adapters.object_storage import S3ObjectStorage
from fitness_bot.infrastructure.adapters.speech_to_text import build_speech_to_text
from fitness_bot.infrastructure.uow.sqlalchemy import SqlAlchemyUow, create_async_session_factory
from fitness_bot.presentation.templates_env import create_jinja_env
from fitness_bot.service.handlers.commands.body import (
    AddCustomMeasurementSiteCommandHandler,
    EnsureDefaultWeightReminderCommandHandler,
    EnsureFixedMeasurementSitesCommandHandler,
    MarkWeightReminderSentCommandHandler,
    RecordMeasurementCommandHandler,
    RecordWeightCommandHandler,
    SeedMeasurementGuidesCommandHandler,
    SetWeightReminderCommandHandler,
)
from fitness_bot.service.handlers.commands.catalog import (
    ApplyCatalogProgramCommandHandler,
    AssignProgramToClientCommandHandler,
    ClaimProgramByCodeCommandHandler,
    PublishProgramCommandHandler,
    SaveProgramDraftCommandHandler,
    UnpublishProgramCommandHandler,
)
from fitness_bot.service.handlers.commands.coach import (
    AcceptCoachInviteCommandHandler,
    ApproveCoachApplicationCommandHandler,
    CreateCoachInviteCommandHandler,
    CreateCoachNoteCommandHandler,
    DeleteCoachReviewCommandHandler,
    GrantModeratorCommandHandler,
    RecordModeratorApplicationMessageCommandHandler,
    RejectCoachApplicationCommandHandler,
    ReportCoachCommandHandler,
    ResolveCoachReportCommandHandler,
    RevokeModeratorCommandHandler,
    SetAcceptingClientsCommandHandler,
    StartCoachClientProgramEditCommandHandler,
    SubmitCoachApplicationCommandHandler,
    SyncUserIdentityCommandHandler,
    UnlinkCoachClientCommandHandler,
    UpsertCoachReviewCommandHandler,
)
from fitness_bot.service.handlers.commands.nutrition import GenerateNutritionCommandHandler
from fitness_bot.service.handlers.commands.program import (
    ApproveProposalCommandHandler,
    ChooseProgramTypeCommandHandler,
    DiscardProposalCommandHandler,
    GenerateNextWeekCommandHandler,
    ProposeProgramChangeCommandHandler,
    ProposeProgramCommandHandler,
    SelectExerciseForProposalCommandHandler,
    UpdateProposalSlotPlannedCommandHandler,
)
from fitness_bot.service.handlers.commands.session import (
    BeginSessionCompletionCommandHandler,
    ConfirmExerciseAsPlannedCommandHandler,
    FinalizeSessionCommandHandler,
    GenerateNextSessionCommandHandler,
    ProposeSessionDeviationCommandHandler,
    ProposeSlotActualCommandHandler,
    ProposeWorkoutChangeCommandHandler,
    RecordSlotActualCommandHandler,
    RememberTechniqueVideoFileIdCommandHandler,
    RestartOpenSessionCommandHandler,
    SaveTechniqueVideoCommandHandler,
    StartSessionFromTemplateCommandHandler,
)
from fitness_bot.service.handlers.commands.users import (
    EnsureUserCommandHandler,
    ExpectInputCommandHandler,
    SetGoalCommandHandler,
    UpdateProfileCommandHandler,
)
from fitness_bot.service.handlers.queries.body import (
    GetMeasurementGuideQueryHandler,
    GetMeasurementHistoryQueryHandler,
    GetWeightHistoryQueryHandler,
    GetWeightReminderQueryHandler,
    ListDueWeightRemindersQueryHandler,
)
from fitness_bot.service.handlers.queries.coach import (
    CountActiveClientsForCoachQueryHandler,
    GetCatalogProgramQueryHandler,
    GetClientCardQueryHandler,
    GetCoachCabinetQueryHandler,
    GetCoachPublicCardQueryHandler,
    ListCoachClientsQueryHandler,
    ListModeratorsQueryHandler,
    ListPendingCoachApplicationsQueryHandler,
    ListProgramCatalogQueryHandler,
    SearchCoachesQueryHandler,
)
from fitness_bot.service.handlers.queries.match_exercises import (
    GetExerciseGuideQueryHandler,
    GetExerciseNamesQueryHandler,
    MatchExercisesQueryHandler,
)
from fitness_bot.service.handlers.queries.nutrition import GetNutritionQueryHandler
from fitness_bot.service.handlers.queries.program import (
    GetActiveProgramQueryHandler,
    GetPendingProposalQueryHandler,
)
from fitness_bot.service.handlers.queries.session import (
    GetSessionDetailQueryHandler,
    GetSessionHistoryQueryHandler,
    GetTodayWorkoutQueryHandler,
    ListClientRecentVideosQueryHandler,
    PrepareTechniqueVideoDeliveryQueryHandler,
)
from fitness_bot.service.handlers.queries.users import (
    GetHomeQueryHandler,
    GetProfileQueryHandler,
    GetWorkflowQueryHandler,
)
from fitness_bot.service.models.commands.body import (
    AddCustomMeasurementSiteCommand,
    EnsureDefaultWeightReminderCommand,
    EnsureFixedMeasurementSitesCommand,
    MarkWeightReminderSentCommand,
    RecordMeasurementCommand,
    RecordWeightCommand,
    SeedMeasurementGuidesCommand,
    SetWeightReminderCommand,
)
from fitness_bot.service.models.commands.catalog import (
    ApplyCatalogProgramCommand,
    AssignProgramToClientCommand,
    ClaimProgramByCodeCommand,
    PublishProgramCommand,
    SaveProgramDraftCommand,
    UnpublishProgramCommand,
)
from fitness_bot.service.models.commands.coach import (
    AcceptCoachInviteCommand,
    ApproveCoachApplicationCommand,
    CreateCoachInviteCommand,
    CreateCoachNoteCommand,
    DeleteCoachReviewCommand,
    GrantModeratorCommand,
    RecordModeratorApplicationMessageCommand,
    RejectCoachApplicationCommand,
    ReportCoachCommand,
    ResolveCoachReportCommand,
    RevokeModeratorCommand,
    SetAcceptingClientsCommand,
    StartCoachClientProgramEditCommand,
    SubmitCoachApplicationCommand,
    SyncUserIdentityCommand,
    UnlinkCoachClientCommand,
    UpsertCoachReviewCommand,
)
from fitness_bot.service.models.commands.nutrition import GenerateNutritionCommand
from fitness_bot.service.models.commands.program import (
    ApproveProposalCommand,
    ChooseProgramTypeCommand,
    DiscardProposalCommand,
    GenerateNextWeekCommand,
    ProposeProgramChangeCommand,
    ProposeProgramCommand,
    SelectExerciseForProposalCommand,
    UpdateProposalSlotPlannedCommand,
)
from fitness_bot.service.models.commands.session import (
    BeginSessionCompletionCommand,
    ConfirmExerciseAsPlannedCommand,
    FinalizeSessionCommand,
    GenerateNextSessionCommand,
    ProposeSessionDeviationCommand,
    ProposeSlotActualCommand,
    ProposeWorkoutChangeCommand,
    RecordSlotActualCommand,
    RememberTechniqueVideoFileIdCommand,
    RestartOpenSessionCommand,
    SaveTechniqueVideoCommand,
    StartSessionFromTemplateCommand,
)
from fitness_bot.service.models.commands.users import (
    EnsureUserCommand,
    ExpectInputCommand,
    SetGoalCommand,
    UpdateProfileCommand,
)
from fitness_bot.service.models.queries.body import (
    GetMeasurementGuideQuery,
    GetMeasurementHistoryQuery,
    GetWeightHistoryQuery,
    GetWeightReminderQuery,
    ListDueWeightRemindersQuery,
)
from fitness_bot.service.models.queries.coach import (
    CountActiveClientsForCoachQuery,
    GetCatalogProgramQuery,
    GetClientCardQuery,
    GetCoachCabinetQuery,
    GetCoachPublicCardQuery,
    ListCoachClientsQuery,
    ListModeratorsQuery,
    ListPendingCoachApplicationsQuery,
    ListProgramCatalogQuery,
    SearchCoachesQuery,
)
from fitness_bot.service.models.queries.match_exercises import (
    GetExerciseGuideQuery,
    GetExerciseNamesQuery,
    MatchExercisesQuery,
)
from fitness_bot.service.models.queries.nutrition import GetNutritionQuery
from fitness_bot.service.models.queries.program import GetActiveProgramQuery, GetPendingProposalQuery
from fitness_bot.service.models.queries.session import (
    GetSessionDetailQuery,
    GetSessionHistoryQuery,
    GetTodayWorkoutQuery,
    ListClientRecentVideosQuery,
    PrepareTechniqueVideoDeliveryQuery,
)
from fitness_bot.service.models.queries.users import GetHomeQuery, GetProfileQuery, GetWorkflowQuery
from fitness_bot.shared.settings import Settings, load_settings


def _build_language_model(settings: Settings):
    if settings.timeweb_api_key.strip() and settings.timeweb_base_url.strip():
        return TimewebLanguageModel(
            api_key=settings.timeweb_api_key,
            base_url=settings.timeweb_base_url,
        )
    return StubLanguageModel()


def _build_object_storage(settings: Settings):
    return S3ObjectStorage(
        endpoint_url=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )


class Container(containers.DeclarativeContainer):
    config = providers.Singleton(load_settings)
    jinja_env = providers.Singleton(create_jinja_env)
    language_model = providers.Singleton(_build_language_model, settings=config)
    speech_to_text = providers.Singleton(
        build_speech_to_text,
        model_dir=config.provided.sherpa_model_dir,
        encoder=config.provided.sherpa_encoder,
        decoder=config.provided.sherpa_decoder,
        joiner=config.provided.sherpa_joiner,
        tokens=config.provided.sherpa_tokens,
        num_threads=config.provided.sherpa_num_threads,
        sample_rate=config.provided.sherpa_sample_rate,
    )
    object_storage = providers.Singleton(_build_object_storage, settings=config)

    session_factory = providers.Singleton(
        create_async_session_factory,
        database_url=config.provided.database_url,
    )
    uow = providers.Factory(SqlAlchemyUow, session_factory=session_factory)
    exercise_catalog = providers.Singleton(SqlAlchemyExerciseCatalog, session_factory=session_factory)

    ensure_user_handler = providers.Factory(EnsureUserCommandHandler, uow=uow)
    update_profile_handler = providers.Factory(UpdateProfileCommandHandler, uow=uow)
    set_goal_handler = providers.Factory(SetGoalCommandHandler, uow=uow)
    expect_input_handler = providers.Factory(ExpectInputCommandHandler, uow=uow)
    record_weight_handler = providers.Factory(RecordWeightCommandHandler, uow=uow)
    set_weight_reminder_handler = providers.Factory(SetWeightReminderCommandHandler, uow=uow)
    ensure_default_weight_reminder_handler = providers.Factory(
        EnsureDefaultWeightReminderCommandHandler,
        uow=uow,
    )
    mark_weight_reminder_sent_handler = providers.Factory(MarkWeightReminderSentCommandHandler, uow=uow)
    record_measurement_handler = providers.Factory(RecordMeasurementCommandHandler, uow=uow)
    add_custom_measurement_site_handler = providers.Factory(AddCustomMeasurementSiteCommandHandler, uow=uow)
    ensure_fixed_measurement_sites_handler = providers.Factory(
        EnsureFixedMeasurementSitesCommandHandler,
        uow=uow,
    )
    seed_measurement_guides_handler = providers.Factory(
        SeedMeasurementGuidesCommandHandler,
        uow=uow,
        language_model=language_model,
    )

    choose_program_type_handler = providers.Factory(ChooseProgramTypeCommandHandler, uow=uow)
    propose_program_handler = providers.Factory(
        ProposeProgramCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    propose_program_change_handler = providers.Factory(
        ProposeProgramChangeCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    select_exercise_for_proposal_handler = providers.Factory(
        SelectExerciseForProposalCommandHandler,
        uow=uow,
        catalog=exercise_catalog,
    )
    update_proposal_slot_planned_handler = providers.Factory(
        UpdateProposalSlotPlannedCommandHandler,
        uow=uow,
    )
    generate_next_week_handler = providers.Factory(
        GenerateNextWeekCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    approve_proposal_handler = providers.Factory(ApproveProposalCommandHandler, uow=uow)
    discard_proposal_handler = providers.Factory(DiscardProposalCommandHandler, uow=uow)
    start_session_from_template_handler = providers.Factory(
        StartSessionFromTemplateCommandHandler,
        uow=uow,
        object_storage=object_storage,
    )
    propose_workout_change_handler = providers.Factory(
        ProposeWorkoutChangeCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    confirm_exercise_as_planned_handler = providers.Factory(ConfirmExerciseAsPlannedCommandHandler, uow=uow)
    record_slot_actual_handler = providers.Factory(RecordSlotActualCommandHandler, uow=uow)
    propose_slot_actual_handler = providers.Factory(
        ProposeSlotActualCommandHandler,
        uow=uow,
        language_model=language_model,
    )
    begin_session_completion_handler = providers.Factory(BeginSessionCompletionCommandHandler, uow=uow)
    restart_open_session_handler = providers.Factory(
        RestartOpenSessionCommandHandler,
        uow=uow,
        object_storage=object_storage,
    )
    propose_session_deviation_handler = providers.Factory(
        ProposeSessionDeviationCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    finalize_session_handler = providers.Factory(FinalizeSessionCommandHandler, uow=uow)
    generate_next_session_handler = providers.Factory(
        GenerateNextSessionCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    generate_nutrition_handler = providers.Factory(
        GenerateNutritionCommandHandler,
        uow=uow,
        language_model=language_model,
    )
    save_technique_video_handler = providers.Factory(
        SaveTechniqueVideoCommandHandler,
        uow=uow,
        object_storage=object_storage,
    )
    remember_technique_video_file_id_handler = providers.Factory(
        RememberTechniqueVideoFileIdCommandHandler,
        uow=uow,
    )

    sync_user_identity_handler = providers.Factory(SyncUserIdentityCommandHandler, uow=uow)
    submit_coach_application_handler = providers.Factory(SubmitCoachApplicationCommandHandler, uow=uow)
    approve_coach_application_handler = providers.Factory(ApproveCoachApplicationCommandHandler, uow=uow)
    reject_coach_application_handler = providers.Factory(RejectCoachApplicationCommandHandler, uow=uow)
    grant_moderator_handler = providers.Factory(GrantModeratorCommandHandler, uow=uow)
    revoke_moderator_handler = providers.Factory(RevokeModeratorCommandHandler, uow=uow)
    create_coach_invite_handler = providers.Factory(CreateCoachInviteCommandHandler, uow=uow)
    accept_coach_invite_handler = providers.Factory(AcceptCoachInviteCommandHandler, uow=uow)
    unlink_coach_client_handler = providers.Factory(UnlinkCoachClientCommandHandler, uow=uow)
    set_accepting_clients_handler = providers.Factory(SetAcceptingClientsCommandHandler, uow=uow)
    upsert_coach_review_handler = providers.Factory(UpsertCoachReviewCommandHandler, uow=uow)
    delete_coach_review_handler = providers.Factory(DeleteCoachReviewCommandHandler, uow=uow)
    report_coach_handler = providers.Factory(ReportCoachCommandHandler, uow=uow)
    resolve_coach_report_handler = providers.Factory(ResolveCoachReportCommandHandler, uow=uow)
    create_coach_note_handler = providers.Factory(CreateCoachNoteCommandHandler, uow=uow)
    record_moderator_application_message_handler = providers.Factory(
        RecordModeratorApplicationMessageCommandHandler,
        uow=uow,
    )
    start_coach_client_program_edit_handler = providers.Factory(
        StartCoachClientProgramEditCommandHandler,
        uow=uow,
    )
    save_program_draft_handler = providers.Factory(SaveProgramDraftCommandHandler, uow=uow)
    publish_program_handler = providers.Factory(PublishProgramCommandHandler, uow=uow)
    unpublish_program_handler = providers.Factory(UnpublishProgramCommandHandler, uow=uow)
    claim_program_by_code_handler = providers.Factory(ClaimProgramByCodeCommandHandler, uow=uow)
    apply_catalog_program_handler = providers.Factory(
        ApplyCatalogProgramCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    assign_program_to_client_handler = providers.Factory(
        AssignProgramToClientCommandHandler,
        uow=uow,
        language_model=language_model,
        catalog=exercise_catalog,
    )
    count_active_clients_handler = providers.Factory(CountActiveClientsForCoachQueryHandler, uow=uow)
    list_pending_coach_applications_handler = providers.Factory(ListPendingCoachApplicationsQueryHandler, uow=uow)
    list_moderators_handler = providers.Factory(ListModeratorsQueryHandler, uow=uow)
    search_coaches_handler = providers.Factory(SearchCoachesQueryHandler, uow=uow)
    get_coach_public_card_handler = providers.Factory(GetCoachPublicCardQueryHandler, uow=uow)
    list_coach_clients_handler = providers.Factory(ListCoachClientsQueryHandler, uow=uow)
    get_client_card_handler = providers.Factory(GetClientCardQueryHandler, uow=uow)
    get_coach_cabinet_handler = providers.Factory(GetCoachCabinetQueryHandler, uow=uow)
    list_program_catalog_handler = providers.Factory(ListProgramCatalogQueryHandler, uow=uow)
    get_catalog_program_handler = providers.Factory(GetCatalogProgramQueryHandler, uow=uow)

    get_profile_handler = providers.Factory(GetProfileQueryHandler, uow=uow)
    get_home_handler = providers.Factory(GetHomeQueryHandler, uow=uow)
    get_workflow_handler = providers.Factory(GetWorkflowQueryHandler, uow=uow)
    get_weight_history_handler = providers.Factory(GetWeightHistoryQueryHandler, uow=uow)
    get_weight_reminder_handler = providers.Factory(GetWeightReminderQueryHandler, uow=uow)
    get_measurement_history_handler = providers.Factory(GetMeasurementHistoryQueryHandler, uow=uow)
    get_measurement_guide_handler = providers.Factory(GetMeasurementGuideQueryHandler, uow=uow)
    list_due_weight_reminders_handler = providers.Factory(ListDueWeightRemindersQueryHandler, uow=uow)
    get_active_program_handler = providers.Factory(GetActiveProgramQueryHandler, uow=uow)
    get_pending_proposal_handler = providers.Factory(GetPendingProposalQueryHandler, uow=uow)
    get_today_workout_handler = providers.Factory(GetTodayWorkoutQueryHandler, uow=uow)
    get_session_history_handler = providers.Factory(GetSessionHistoryQueryHandler, uow=uow)
    get_session_detail_handler = providers.Factory(
        GetSessionDetailQueryHandler,
        uow=uow,
        catalog=exercise_catalog,
    )
    prepare_technique_video_delivery_handler = providers.Factory(
        PrepareTechniqueVideoDeliveryQueryHandler,
        uow=uow,
        object_storage=object_storage,
        catalog=exercise_catalog,
    )
    list_client_recent_videos_handler = providers.Factory(
        ListClientRecentVideosQueryHandler,
        uow=uow,
        catalog=exercise_catalog,
    )
    get_nutrition_handler = providers.Factory(GetNutritionQueryHandler, uow=uow)
    match_exercises_handler = providers.Factory(MatchExercisesQueryHandler, catalog=exercise_catalog)
    get_exercise_names_handler = providers.Factory(GetExerciseNamesQueryHandler, catalog=exercise_catalog)
    get_exercise_guide_handler = providers.Factory(GetExerciseGuideQueryHandler, catalog=exercise_catalog)


def build_request_map() -> cqrs.RequestMap:
    request_map = cqrs.RequestMap()
    request_map.bind(EnsureUserCommand, EnsureUserCommandHandler)
    request_map.bind(UpdateProfileCommand, UpdateProfileCommandHandler)
    request_map.bind(SetGoalCommand, SetGoalCommandHandler)
    request_map.bind(ExpectInputCommand, ExpectInputCommandHandler)
    request_map.bind(RecordWeightCommand, RecordWeightCommandHandler)
    request_map.bind(SetWeightReminderCommand, SetWeightReminderCommandHandler)
    request_map.bind(EnsureDefaultWeightReminderCommand, EnsureDefaultWeightReminderCommandHandler)
    request_map.bind(MarkWeightReminderSentCommand, MarkWeightReminderSentCommandHandler)
    request_map.bind(RecordMeasurementCommand, RecordMeasurementCommandHandler)
    request_map.bind(AddCustomMeasurementSiteCommand, AddCustomMeasurementSiteCommandHandler)
    request_map.bind(EnsureFixedMeasurementSitesCommand, EnsureFixedMeasurementSitesCommandHandler)
    request_map.bind(SeedMeasurementGuidesCommand, SeedMeasurementGuidesCommandHandler)
    request_map.bind(ChooseProgramTypeCommand, ChooseProgramTypeCommandHandler)
    request_map.bind(ProposeProgramCommand, ProposeProgramCommandHandler)
    request_map.bind(ProposeProgramChangeCommand, ProposeProgramChangeCommandHandler)
    request_map.bind(SelectExerciseForProposalCommand, SelectExerciseForProposalCommandHandler)
    request_map.bind(UpdateProposalSlotPlannedCommand, UpdateProposalSlotPlannedCommandHandler)
    request_map.bind(GenerateNextWeekCommand, GenerateNextWeekCommandHandler)
    request_map.bind(ApproveProposalCommand, ApproveProposalCommandHandler)
    request_map.bind(DiscardProposalCommand, DiscardProposalCommandHandler)
    request_map.bind(StartSessionFromTemplateCommand, StartSessionFromTemplateCommandHandler)
    request_map.bind(ProposeWorkoutChangeCommand, ProposeWorkoutChangeCommandHandler)
    request_map.bind(ConfirmExerciseAsPlannedCommand, ConfirmExerciseAsPlannedCommandHandler)
    request_map.bind(RecordSlotActualCommand, RecordSlotActualCommandHandler)
    request_map.bind(ProposeSlotActualCommand, ProposeSlotActualCommandHandler)
    request_map.bind(BeginSessionCompletionCommand, BeginSessionCompletionCommandHandler)
    request_map.bind(RestartOpenSessionCommand, RestartOpenSessionCommandHandler)
    request_map.bind(ProposeSessionDeviationCommand, ProposeSessionDeviationCommandHandler)
    request_map.bind(FinalizeSessionCommand, FinalizeSessionCommandHandler)
    request_map.bind(GenerateNextSessionCommand, GenerateNextSessionCommandHandler)
    request_map.bind(SaveTechniqueVideoCommand, SaveTechniqueVideoCommandHandler)
    request_map.bind(RememberTechniqueVideoFileIdCommand, RememberTechniqueVideoFileIdCommandHandler)
    request_map.bind(GenerateNutritionCommand, GenerateNutritionCommandHandler)
    request_map.bind(GetProfileQuery, GetProfileQueryHandler)
    request_map.bind(GetHomeQuery, GetHomeQueryHandler)
    request_map.bind(GetWorkflowQuery, GetWorkflowQueryHandler)
    request_map.bind(GetWeightHistoryQuery, GetWeightHistoryQueryHandler)
    request_map.bind(GetWeightReminderQuery, GetWeightReminderQueryHandler)
    request_map.bind(GetMeasurementHistoryQuery, GetMeasurementHistoryQueryHandler)
    request_map.bind(GetMeasurementGuideQuery, GetMeasurementGuideQueryHandler)
    request_map.bind(ListDueWeightRemindersQuery, ListDueWeightRemindersQueryHandler)
    request_map.bind(GetActiveProgramQuery, GetActiveProgramQueryHandler)
    request_map.bind(GetPendingProposalQuery, GetPendingProposalQueryHandler)
    request_map.bind(GetTodayWorkoutQuery, GetTodayWorkoutQueryHandler)
    request_map.bind(GetSessionHistoryQuery, GetSessionHistoryQueryHandler)
    request_map.bind(GetSessionDetailQuery, GetSessionDetailQueryHandler)
    request_map.bind(PrepareTechniqueVideoDeliveryQuery, PrepareTechniqueVideoDeliveryQueryHandler)
    request_map.bind(ListClientRecentVideosQuery, ListClientRecentVideosQueryHandler)
    request_map.bind(GetNutritionQuery, GetNutritionQueryHandler)
    request_map.bind(MatchExercisesQuery, MatchExercisesQueryHandler)
    request_map.bind(GetExerciseNamesQuery, GetExerciseNamesQueryHandler)
    request_map.bind(SyncUserIdentityCommand, SyncUserIdentityCommandHandler)
    request_map.bind(SubmitCoachApplicationCommand, SubmitCoachApplicationCommandHandler)
    request_map.bind(ApproveCoachApplicationCommand, ApproveCoachApplicationCommandHandler)
    request_map.bind(RejectCoachApplicationCommand, RejectCoachApplicationCommandHandler)
    request_map.bind(GrantModeratorCommand, GrantModeratorCommandHandler)
    request_map.bind(RevokeModeratorCommand, RevokeModeratorCommandHandler)
    request_map.bind(CreateCoachInviteCommand, CreateCoachInviteCommandHandler)
    request_map.bind(AcceptCoachInviteCommand, AcceptCoachInviteCommandHandler)
    request_map.bind(UnlinkCoachClientCommand, UnlinkCoachClientCommandHandler)
    request_map.bind(SetAcceptingClientsCommand, SetAcceptingClientsCommandHandler)
    request_map.bind(UpsertCoachReviewCommand, UpsertCoachReviewCommandHandler)
    request_map.bind(DeleteCoachReviewCommand, DeleteCoachReviewCommandHandler)
    request_map.bind(ReportCoachCommand, ReportCoachCommandHandler)
    request_map.bind(ResolveCoachReportCommand, ResolveCoachReportCommandHandler)
    request_map.bind(CreateCoachNoteCommand, CreateCoachNoteCommandHandler)
    request_map.bind(RecordModeratorApplicationMessageCommand, RecordModeratorApplicationMessageCommandHandler)
    request_map.bind(StartCoachClientProgramEditCommand, StartCoachClientProgramEditCommandHandler)
    request_map.bind(SaveProgramDraftCommand, SaveProgramDraftCommandHandler)
    request_map.bind(PublishProgramCommand, PublishProgramCommandHandler)
    request_map.bind(UnpublishProgramCommand, UnpublishProgramCommandHandler)
    request_map.bind(ClaimProgramByCodeCommand, ClaimProgramByCodeCommandHandler)
    request_map.bind(ApplyCatalogProgramCommand, ApplyCatalogProgramCommandHandler)
    request_map.bind(AssignProgramToClientCommand, AssignProgramToClientCommandHandler)
    request_map.bind(CountActiveClientsForCoachQuery, CountActiveClientsForCoachQueryHandler)
    request_map.bind(ListPendingCoachApplicationsQuery, ListPendingCoachApplicationsQueryHandler)
    request_map.bind(ListModeratorsQuery, ListModeratorsQueryHandler)
    request_map.bind(SearchCoachesQuery, SearchCoachesQueryHandler)
    request_map.bind(GetCoachPublicCardQuery, GetCoachPublicCardQueryHandler)
    request_map.bind(ListCoachClientsQuery, ListCoachClientsQueryHandler)
    request_map.bind(GetClientCardQuery, GetClientCardQueryHandler)
    request_map.bind(GetCoachCabinetQuery, GetCoachCabinetQueryHandler)
    request_map.bind(ListProgramCatalogQuery, ListProgramCatalogQueryHandler)
    request_map.bind(GetCatalogProgramQuery, GetCatalogProgramQueryHandler)
    request_map.bind(GetExerciseGuideQuery, GetExerciseGuideQueryHandler)
    return request_map


def build_mediator(container: Container) -> cqrs.RequestMediator:
    cqrs_container = DependencyInjectorCQRSContainer()
    cqrs_container.attach_external_container(container)
    return cqrs.RequestMediator(request_map=build_request_map(), container=cqrs_container)


def build_container() -> Container:
    container = Container()
    settings: Settings = container.config()
    _ = settings
    return container
