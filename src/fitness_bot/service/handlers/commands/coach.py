from __future__ import annotations

import cqrs

from fitness_bot.domain.coach.application import CoachApplication, CoachApplicationModeratorMessage
from fitness_bot.domain.coach.invite import CoachInvite
from fitness_bot.domain.coach.link import CoachClientLink
from fitness_bot.domain.coach.note import CoachNote
from fitness_bot.domain.coach.profile import CoachProfile
from fitness_bot.domain.coach.report import CoachReport
from fitness_bot.domain.coach.review import CoachReview
from fitness_bot.domain.enums import CoachApplicationStatus, CoachNoteVisibility
from fitness_bot.domain.errors import DomainError
from fitness_bot.domain.users.user import User
from fitness_bot.service.authz import require_coach_of, require_moderator, require_verified_coach
from fitness_bot.service.interfaces.uow import IUow
from fitness_bot.service.models.commands import coach as cmds


def _require_user(user: User | None) -> User:
    if user is None:
        raise DomainError("user not found")
    return user


def _message_refs(messages: list[CoachApplicationModeratorMessage]) -> list[dict]:
    return [
        {
            "chat_id": item.chat_id,
            "message_id": item.message_id,
            "media_message_id": item.media_message_id,
            "moderator_user_id": str(item.moderator_user_id),
        }
        for item in messages
    ]


class SyncUserIdentityCommandHandler(
    cqrs.RequestHandler[cmds.SyncUserIdentityCommand, cmds.SyncUserIdentityCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SyncUserIdentityCommand) -> cmds.SyncUserIdentityCommandResult:
        async with self._uow.transaction() as repos:
            user, _ = await repos.users.ensure(
                telegram_user_id=request.telegram_user_id,
                chat_id=request.chat_id,
            )
            user.sync_telegram_identity(
                display_name=request.display_name,
                telegram_username=request.telegram_username,
            )
            if request.telegram_user_id in set(request.bootstrap_moderator_ids) and not user.is_moderator:
                user.grant_moderator()
            await repos.users.save(user)
            return cmds.SyncUserIdentityCommandResult(user_id=user.id, is_moderator=user.is_moderator)


class SubmitCoachApplicationCommandHandler(
    cqrs.RequestHandler[cmds.SubmitCoachApplicationCommand, cmds.SubmitCoachApplicationCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SubmitCoachApplicationCommand) -> cmds.SubmitCoachApplicationCommandResult:
        async with self._uow.transaction() as repos:
            user = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            application = CoachApplication.submit(
                user_id=user.id,
                display_name=request.display_name,
                bio=request.bio,
                portfolio_url=request.portfolio_url,
                credential_object_key=request.credential_object_key,
                credential_content_type=request.credential_content_type,
                credential_byte_size=request.credential_byte_size,
                credential_caption=request.credential_caption,
            )
            saved = await repos.coaches.add_application(application)
            profile = await repos.coaches.get_profile(user.id)
            if profile is None:
                profile = CoachProfile.create(
                    user_id=user.id,
                    display_name=request.display_name,
                    bio=request.bio,
                    portfolio_url=request.portfolio_url,
                )
            else:
                profile.display_name = request.display_name.strip()
                profile.bio = request.bio.strip()
                profile.portfolio_url = request.portfolio_url.strip()
            profile.mark_pending()
            await repos.coaches.save_profile(profile)
            moderators = await repos.users.list_moderators()
            return cmds.SubmitCoachApplicationCommandResult(
                application_id=saved.id,
                moderator_user_ids=[item.id for item in moderators],
                moderator_chats=[{"user_id": str(item.id), "chat_id": item.chat_id} for item in moderators],
                display_name=saved.display_name,
                bio=saved.bio,
                portfolio_url=saved.portfolio_url,
                credential_object_key=saved.credential_object_key,
                credential_content_type=saved.credential_content_type,
            )


class ApproveCoachApplicationCommandHandler(
    cqrs.RequestHandler[cmds.ApproveCoachApplicationCommand, cmds.ApproveCoachApplicationCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ApproveCoachApplicationCommand) -> cmds.ApproveCoachApplicationCommandResult:
        async with self._uow.transaction() as repos:
            actor = require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            application = await repos.coaches.get_application(request.application_id)
            if application is None:
                raise DomainError("application not found")
            messages = await repos.coaches.list_moderator_messages(application.id)
            applicant = await repos.users.get_by_id(application.user_id)
            status_text = f"✅ Заявка одобрена · {application.display_name}"
            if application.status != CoachApplicationStatus.PENDING:
                return cmds.ApproveCoachApplicationCommandResult(
                    application_id=application.id,
                    already_processed=True,
                    applicant_user_id=application.user_id,
                    applicant_chat_id=applicant.chat_id if applicant else None,
                    moderator_message_refs=_message_refs(messages),
                    status_text=status_text,
                )
            application.approve(moderator_user_id=actor.id)
            resolved = await repos.coaches.resolve_application_if_pending(application)
            if resolved is None:
                fresh = await repos.coaches.get_application(application.id)
                messages = await repos.coaches.list_moderator_messages(application.id)
                return cmds.ApproveCoachApplicationCommandResult(
                    application_id=application.id,
                    already_processed=True,
                    applicant_user_id=fresh.user_id if fresh else application.user_id,
                    applicant_chat_id=applicant.chat_id if applicant else None,
                    moderator_message_refs=_message_refs(messages),
                    status_text=status_text,
                )
            profile = await repos.coaches.get_profile(resolved.user_id)
            if profile is None:
                profile = CoachProfile.create(
                    user_id=resolved.user_id,
                    display_name=resolved.display_name,
                    bio=resolved.bio,
                    portfolio_url=resolved.portfolio_url,
                )
            profile.mark_verified()
            await repos.coaches.save_profile(profile)
            return cmds.ApproveCoachApplicationCommandResult(
                application_id=resolved.id,
                applicant_user_id=resolved.user_id,
                applicant_chat_id=applicant.chat_id if applicant else None,
                moderator_message_refs=_message_refs(messages),
                status_text=status_text,
            )


class RejectCoachApplicationCommandHandler(
    cqrs.RequestHandler[cmds.RejectCoachApplicationCommand, cmds.RejectCoachApplicationCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RejectCoachApplicationCommand) -> cmds.RejectCoachApplicationCommandResult:
        async with self._uow.transaction() as repos:
            actor = require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            application = await repos.coaches.get_application(request.application_id)
            if application is None:
                raise DomainError("application not found")
            messages = await repos.coaches.list_moderator_messages(application.id)
            applicant = await repos.users.get_by_id(application.user_id)
            if application.status != CoachApplicationStatus.PENDING:
                comment = application.moderator_comment or ""
                status_text = f"❌ Заявка отклонена · {application.display_name}"
                if comment:
                    status_text = f"{status_text}: {comment}"
                return cmds.RejectCoachApplicationCommandResult(
                    application_id=application.id,
                    already_processed=True,
                    applicant_user_id=application.user_id,
                    applicant_chat_id=applicant.chat_id if applicant else None,
                    moderator_comment=application.moderator_comment,
                    moderator_message_refs=_message_refs(messages),
                    status_text=status_text,
                )
            application.reject(moderator_user_id=actor.id, comment=request.comment)
            resolved = await repos.coaches.resolve_application_if_pending(application)
            if resolved is None:
                fresh = await repos.coaches.get_application(application.id)
                comment = (fresh.moderator_comment if fresh else None) or request.comment
                status_text = f"❌ Заявка отклонена · {application.display_name}: {comment}"
                return cmds.RejectCoachApplicationCommandResult(
                    application_id=application.id,
                    already_processed=True,
                    applicant_user_id=fresh.user_id if fresh else application.user_id,
                    applicant_chat_id=applicant.chat_id if applicant else None,
                    moderator_comment=fresh.moderator_comment if fresh else None,
                    moderator_message_refs=_message_refs(messages),
                    status_text=status_text,
                )
            profile = await repos.coaches.get_profile(resolved.user_id)
            if profile is not None:
                profile.mark_rejected()
                await repos.coaches.save_profile(profile)
            status_text = (
                f"❌ Заявка отклонена · {resolved.display_name}: {resolved.moderator_comment or request.comment}"
            )
            return cmds.RejectCoachApplicationCommandResult(
                application_id=resolved.id,
                applicant_user_id=resolved.user_id,
                applicant_chat_id=applicant.chat_id if applicant else None,
                moderator_comment=resolved.moderator_comment,
                moderator_message_refs=_message_refs(messages),
                status_text=status_text,
            )


class GrantModeratorCommandHandler(
    cqrs.RequestHandler[cmds.GrantModeratorCommand, cmds.GrantModeratorCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.GrantModeratorCommand) -> cmds.GrantModeratorCommandResult:
        async with self._uow.transaction() as repos:
            require_moderator(_require_user(await repos.users.get_by_telegram_id(request.actor_telegram_user_id)))
            target = _require_user(await repos.users.get_by_telegram_id(request.target_telegram_user_id))
            target.grant_moderator()
            await repos.users.save(target)
            return cmds.GrantModeratorCommandResult(target_user_id=target.id)


class RevokeModeratorCommandHandler(
    cqrs.RequestHandler[cmds.RevokeModeratorCommand, cmds.RevokeModeratorCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.RevokeModeratorCommand) -> cmds.RevokeModeratorCommandResult:
        async with self._uow.transaction() as repos:
            actor = require_moderator(
                _require_user(await repos.users.get_by_telegram_id(request.actor_telegram_user_id)),
            )
            target = _require_user(await repos.users.get_by_telegram_id(request.target_telegram_user_id))
            if target.id == actor.id and await repos.users.count_moderators() <= 1:
                raise DomainError("cannot revoke the last moderator")
            if target.is_moderator and await repos.users.count_moderators() <= 1:
                raise DomainError("cannot revoke the last moderator")
            target.revoke_moderator()
            await repos.users.save(target)
            return cmds.RevokeModeratorCommandResult(target_user_id=target.id)


class CreateCoachInviteCommandHandler(
    cqrs.RequestHandler[cmds.CreateCoachInviteCommand, cmds.CreateCoachInviteCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.CreateCoachInviteCommand) -> cmds.CreateCoachInviteCommandResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_verified_coach(repos, actor)
            previous = await repos.coaches.get_active_invite(actor.id)
            revoked_previous = False
            if previous is not None:
                previous.revoke()
                await repos.coaches.save_invite(previous)
                revoked_previous = True
            invite = CoachInvite.create(coach_user_id=actor.id)
            saved = await repos.coaches.save_invite(invite)
            return cmds.CreateCoachInviteCommandResult(
                invite_id=saved.id,
                code=saved.code,
                revoked_previous=revoked_previous,
            )


class AcceptCoachInviteCommandHandler(
    cqrs.RequestHandler[cmds.AcceptCoachInviteCommand, cmds.AcceptCoachInviteCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.AcceptCoachInviteCommand) -> cmds.AcceptCoachInviteCommandResult:
        async with self._uow.transaction() as repos:
            client = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            invite = await repos.coaches.get_invite_by_code(request.code)
            if invite is None or not invite.is_active:
                raise DomainError("invite not found or inactive")
            if client.id == invite.coach_user_id:
                raise DomainError("cannot link to yourself")
            profile = await repos.coaches.get_profile(invite.coach_user_id)
            if profile is None or not profile.is_verified:
                raise DomainError("coach is not verified")
            if not profile.accepting_clients:
                raise DomainError("coach is not accepting clients")
            previous = await repos.coaches.get_active_link(client_user_id=client.id)
            previous_coach_id = None
            if previous is not None:
                if previous.coach_user_id == invite.coach_user_id:
                    return cmds.AcceptCoachInviteCommandResult(
                        link_id=previous.id,
                        coach_user_id=previous.coach_user_id,
                        previous_coach_user_id=None,
                    )
                previous.revoke(actor_user_id=client.id)
                await repos.coaches.save_link(previous)
                previous_coach_id = previous.coach_user_id
            link = CoachClientLink.activate(coach_user_id=invite.coach_user_id, client_user_id=client.id)
            saved = await repos.coaches.save_link(link)
            invite.record_use()
            await repos.coaches.save_invite(invite)
            return cmds.AcceptCoachInviteCommandResult(
                link_id=saved.id,
                coach_user_id=saved.coach_user_id,
                previous_coach_user_id=previous_coach_id,
            )


class UnlinkCoachClientCommandHandler(
    cqrs.RequestHandler[cmds.UnlinkCoachClientCommand, cmds.UnlinkCoachClientCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.UnlinkCoachClientCommand) -> cmds.UnlinkCoachClientCommandResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            link = None
            if request.link_id is not None:
                link = await repos.coaches.get_link(request.link_id)
            elif request.client_user_id is not None:
                link = await repos.coaches.get_active_link(
                    coach_user_id=actor.id,
                    client_user_id=request.client_user_id,
                )
            elif request.coach_user_id is not None:
                link = await repos.coaches.get_active_link(
                    coach_user_id=request.coach_user_id,
                    client_user_id=actor.id,
                )
            else:
                link = await repos.coaches.get_active_link(client_user_id=actor.id)
                if link is None:
                    link = await repos.coaches.get_active_link(coach_user_id=actor.id)
            if link is None:
                raise DomainError("link not found")
            link.revoke(actor_user_id=actor.id)
            saved = await repos.coaches.save_link(link)
            other = saved.client_user_id if actor.id == saved.coach_user_id else saved.coach_user_id
            return cmds.UnlinkCoachClientCommandResult(
                link_id=saved.id,
                coach_user_id=saved.coach_user_id,
                client_user_id=saved.client_user_id,
                other_party_user_id=other,
            )


class SetAcceptingClientsCommandHandler(
    cqrs.RequestHandler[cmds.SetAcceptingClientsCommand, cmds.SetAcceptingClientsCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.SetAcceptingClientsCommand) -> cmds.SetAcceptingClientsCommandResult:
        async with self._uow.transaction() as repos:
            actor = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            profile = await require_verified_coach(repos, actor)
            profile.set_accepting_clients(request.accepting)
            saved = await repos.coaches.save_profile(profile)
            return cmds.SetAcceptingClientsCommandResult(accepting_clients=saved.accepting_clients)


class UpsertCoachReviewCommandHandler(
    cqrs.RequestHandler[cmds.UpsertCoachReviewCommand, cmds.UpsertCoachReviewCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.UpsertCoachReviewCommand) -> cmds.UpsertCoachReviewCommandResult:
        async with self._uow.transaction() as repos:
            author = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if not await repos.coaches.has_any_link(coach_user_id=request.coach_user_id, client_user_id=author.id):
                raise DomainError("review requires past or current coach link")
            existing = await repos.coaches.get_review(
                coach_user_id=request.coach_user_id,
                author_user_id=author.id,
            )
            if existing is None:
                review = CoachReview.create(
                    coach_user_id=request.coach_user_id,
                    author_user_id=author.id,
                    stars=request.stars,
                    body=request.body,
                )
            else:
                existing.update(stars=request.stars, body=request.body)
                review = existing
            saved = await repos.coaches.upsert_review(review)
            profile = await repos.coaches.recompute_rating(request.coach_user_id)
            return cmds.UpsertCoachReviewCommandResult(
                review_id=saved.id,
                rating_avg=float(profile.rating_avg) if profile and profile.rating_avg is not None else None,
                rating_count=profile.rating_count if profile else 0,
            )


class DeleteCoachReviewCommandHandler(
    cqrs.RequestHandler[cmds.DeleteCoachReviewCommand, cmds.DeleteCoachReviewCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.DeleteCoachReviewCommand) -> cmds.DeleteCoachReviewCommandResult:
        async with self._uow.transaction() as repos:
            author = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            existing = await repos.coaches.get_review(
                coach_user_id=request.coach_user_id,
                author_user_id=author.id,
            )
            if existing is None:
                return cmds.DeleteCoachReviewCommandResult(deleted=False)
            await repos.coaches.delete_review(coach_user_id=request.coach_user_id, author_user_id=author.id)
            await repos.coaches.recompute_rating(request.coach_user_id)
            return cmds.DeleteCoachReviewCommandResult(deleted=True)


class ReportCoachCommandHandler(
    cqrs.RequestHandler[cmds.ReportCoachCommand, cmds.ReportCoachCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ReportCoachCommand) -> cmds.ReportCoachCommandResult:
        async with self._uow.transaction() as repos:
            reporter = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            if not await repos.coaches.has_any_link(
                coach_user_id=request.coach_user_id,
                client_user_id=reporter.id,
            ):
                raise DomainError("report requires past or current coach link")
            open_report = await repos.coaches.get_open_report(
                reporter_user_id=reporter.id,
                coach_user_id=request.coach_user_id,
            )
            if open_report is not None:
                raise DomainError("open report already exists")
            report = CoachReport.create(
                reporter_user_id=reporter.id,
                coach_user_id=request.coach_user_id,
                body=request.body,
            )
            saved = await repos.coaches.add_report(report)
            moderators = await repos.users.list_moderators()
            return cmds.ReportCoachCommandResult(
                report_id=saved.id,
                moderator_user_ids=[item.id for item in moderators],
            )


class ResolveCoachReportCommandHandler(
    cqrs.RequestHandler[cmds.ResolveCoachReportCommand, cmds.ResolveCoachReportCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.ResolveCoachReportCommand) -> cmds.ResolveCoachReportCommandResult:
        async with self._uow.transaction() as repos:
            require_moderator(_require_user(await repos.users.get_by_telegram_id(request.telegram_user_id)))
            report = await repos.coaches.get_report(request.report_id)
            if report is None:
                raise DomainError("report not found")
            report.resolve()
            await repos.coaches.save_report(report)
            suspended = False
            if request.suspend:
                profile = await repos.coaches.get_profile(report.coach_user_id)
                if profile is not None and profile.is_verified:
                    profile.suspend()
                    await repos.coaches.save_profile(profile)
                    suspended = True
            return cmds.ResolveCoachReportCommandResult(report_id=report.id, suspended=suspended)


class CreateCoachNoteCommandHandler(
    cqrs.RequestHandler[cmds.CreateCoachNoteCommand, cmds.CreateCoachNoteCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(self, request: cmds.CreateCoachNoteCommand) -> cmds.CreateCoachNoteCommandResult:
        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_coach_of(repos, coach, request.client_user_id)
            note = CoachNote.create(
                coach_user_id=coach.id,
                client_user_id=request.client_user_id,
                visibility=request.visibility,
                body=request.body,
                session_id=request.session_id,
                slot_id=request.slot_id,
            )
            saved = await repos.coaches.add_note(note)
            client = await repos.users.get_by_id(request.client_user_id)
            return cmds.CreateCoachNoteCommandResult(
                note_id=saved.id,
                visibility=saved.visibility,
                client_chat_id=client.chat_id if client and saved.visibility == CoachNoteVisibility.SHARED else None,
                coach_username=coach.telegram_username,
            )


class RecordModeratorApplicationMessageCommandHandler(
    cqrs.RequestHandler[
        cmds.RecordModeratorApplicationMessageCommand,
        cmds.RecordModeratorApplicationMessageCommandResult,
    ],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.RecordModeratorApplicationMessageCommand,
    ) -> cmds.RecordModeratorApplicationMessageCommandResult:
        async with self._uow.transaction() as repos:
            message = CoachApplicationModeratorMessage(
                application_id=request.application_id,
                moderator_user_id=request.moderator_user_id,
                chat_id=request.chat_id,
                message_id=request.message_id,
                media_message_id=request.media_message_id,
            )
            saved = await repos.coaches.add_moderator_message(message)
            return cmds.RecordModeratorApplicationMessageCommandResult(message_id=saved.id)


class StartCoachClientProgramEditCommandHandler(
    cqrs.RequestHandler[cmds.StartCoachClientProgramEditCommand, cmds.StartCoachClientProgramEditCommandResult],
):
    def __init__(self, uow: IUow) -> None:
        self._uow = uow

    async def handle(
        self,
        request: cmds.StartCoachClientProgramEditCommand,
    ) -> cmds.StartCoachClientProgramEditCommandResult:
        from fitness_bot.domain.enums import ExpectedInput, ProgramType
        from fitness_bot.domain.workout.document import WorkoutDocument
        from fitness_bot.domain.workout.proposal import Proposal
        from fitness_bot.service.handlers.commands.program import _replace_pending

        async with self._uow.transaction() as repos:
            coach = _require_user(await repos.users.get_by_telegram_id(request.telegram_user_id))
            await require_coach_of(repos, coach, request.client_user_id)
            client = _require_user(await repos.users.get_by_id(request.client_user_id))
            program = None
            if client.active_program_id is not None:
                program = await repos.programs.get_by_id(client.active_program_id)
            if program is not None:
                document = program.to_document()
                proposal = Proposal.new_program_document(
                    user_id=client.id,
                    program_type=document.program_type,
                    document=document,
                    reply="Текущий план клиента. Опишите правки текстом.",
                    base_program_id=program.id,
                )
            else:
                document = WorkoutDocument(program_type=ProgramType.FULL_BODY, days=[])
                proposal = Proposal.new_program_document(
                    user_id=client.id,
                    program_type=ProgramType.FULL_BODY,
                    document=document,
                    reply="У клиента нет активного плана. Опишите программу текстом.",
                )
            saved = await _replace_pending(repos, client, proposal)
            coach.expect_input(ExpectedInput.COACH_EDIT_CLIENT, expected_field=str(client.id))
            await repos.users.save(coach)
            return cmds.StartCoachClientProgramEditCommandResult(
                client_user_id=client.id,
                proposal_id=saved.id,
                document=saved.document,
                program_type=saved.program_type,
                has_active_program=program is not None,
            )
