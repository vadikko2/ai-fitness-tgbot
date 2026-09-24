from __future__ import annotations

from enum import StrEnum


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class Goal(StrEnum):
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    STRENGTH = "strength"
    MAINTENANCE = "maintenance"
    RECOVERY = "recovery"
    STAY_FIT = "stay_fit"
    HEALTHY_LIFESTYLE = "healthy_lifestyle"


class ExpectedInput(StrEnum):
    NONE = "none"
    PROFILE_FIELD = "profile_field"
    WEIGHT = "weight"
    MEASUREMENT_VALUE = "measurement_value"
    PROPOSAL_UTTERANCE = "proposal_utterance"
    COMPLETION_DEVIATION = "completion_deviation"
    TECHNIQUE_VIDEO = "technique_video"
    SLOT_WEIGHT = "slot_weight"
    SLOT_LOAD = "slot_load"
    CODE_OR_LINK = "code_or_link"
    COACH_NOTE = "coach_note"
    COACH_FEEDBACK = "coach_feedback"
    COACH_APPLICATION = "coach_application"
    COACH_CREDENTIAL = "coach_credential"
    MODERATOR_REJECT_COMMENT = "moderator_reject_comment"
    COACH_REVIEW = "coach_review"
    COACH_REPORT = "coach_report"
    COACH_EDIT_CLIENT = "coach_edit_client"
    PROGRESS_PHOTO = "progress_photo"
    FEEDBACK_TEXT = "feedback_text"
    FEEDBACK_PHOTO = "feedback_photo"
    FEEDBACK_CANCEL_REPLY = "feedback_cancel_reply"


class ProgressPhotoAngle(StrEnum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class WeightSource(StrEnum):
    ONBOARDING = "onboarding"
    MANUAL = "manual"
    REMINDER = "reminder"


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    HIGH = "high"


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Supplement(StrEnum):
    NONE = "none"
    PROTEIN = "protein"
    CREATINE = "creatine"
    CAFFEINE_PREWORKOUT = "caffeine_preworkout"
    VITAMINS_OMEGA = "vitamins_omega"
    OTHER = "other"


class ProfileField(StrEnum):
    SEX = "sex"
    BIRTH_YEAR = "birth_year"
    HEIGHT = "height"
    WEIGHT = "weight"
    EXPERIENCE = "experience"
    EXPERIENCE_DETAILS = "experience_details"
    DAYS_PER_WEEK = "days_per_week"
    TRAINING_WEEKDAYS = "training_weekdays"
    EQUIPMENT = "equipment"
    LIMITATIONS = "limitations"
    ACTIVITY_LEVEL = "activity_level"
    SESSION_MINUTES = "session_minutes"
    BODY_FAT = "body_fat"
    SUPPLEMENTS = "supplements"
    DIET_PREFS = "diet_prefs"
    PHARMA = "pharma"
    TIMEZONE = "timezone"


SESSION_MINUTES_CHOICES: frozenset[int] = frozenset({30, 45, 60, 90})


class ProgramType(StrEnum):
    FULL_BODY = "full_body"
    UPPER_LOWER = "upper_lower"
    PUSH_PULL = "push_pull"
    ANTAGONIST = "antagonist"
    SYNERGIST = "synergist"
    SPLIT = "split"


class TrainingStyle(StrEnum):
    CLASSIC = "classic"
    STRENGTH = "strength"
    CIRCUIT = "circuit"
    HIT = "hit"


class WorkoutIntensity(StrEnum):
    RECOVERY = "recovery"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class ProgramStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ACTIVE = "active"
    ARCHIVED = "archived"


class CoachVerificationStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class CoachApplicationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CoachLinkStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


class CoachNoteVisibility(StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


class CoachReportStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class FeedbackKind(StrEnum):
    IDEA = "idea"
    PROBLEM = "problem"


class FeedbackStatus(StrEnum):
    DRAFT = "draft"
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class ProposalKind(StrEnum):
    PROGRAM = "program"
    WORKOUT_EDIT = "workout_edit"
    PERFORMANCE = "performance"
    NEXT_SESSION = "next_session"
    COMPLETION_DEVIATION = "completion_deviation"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISCARDED = "discarded"


class SessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    PENDING_COMPLETION = "pending_completion"
    COMPLETED = "completed"
