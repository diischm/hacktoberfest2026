from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from reports.choices import VerificationStatus
from reports.models import Report, ReportFeedback


class ReportFeedbackInline(admin.TabularInline):
    """Shows rider votes on the report page. Read-only: votes come from the API, not admins."""

    model = ReportFeedback
    fields = ("action", "session_key", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hazard_type",
        "verification_status",
        "needs_review",
        "ai_confidence",
        "is_synthetic",
        "created_at",
    )
    list_filter = ("hazard_type", "verification_status", "needs_review", "is_synthetic")
    search_fields = ("description", "note")
    readonly_fields = ("photo_preview", "ai_raw_response")
    inlines = (ReportFeedbackInline,)
    actions = ("mark_verified", "mark_resolved", "mark_disputed")

    @admin.display(description="Photo preview")
    def photo_preview(self, obj):
        if not obj.photo:
            return "No photo"
        # format_html escapes the URL, so a weird file name can't inject HTML.
        return format_html(
            '<a href="{0}"><img src="{0}" alt="Report photo" style="max-height:240px"></a>',
            obj.photo.url,
        )

    @admin.action(description="Mark verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verification_status=VerificationStatus.VERIFIED, resolved_at=None)
        self.message_user(request, f"{updated} report(s) marked verified.")

    @admin.action(description="Mark resolved")
    def mark_resolved(self, request, queryset):
        updated = queryset.update(
            verification_status=VerificationStatus.RESOLVED, resolved_at=timezone.now()
        )
        self.message_user(request, f"{updated} report(s) marked resolved.")

    @admin.action(description="Mark disputed")
    def mark_disputed(self, request, queryset):
        updated = queryset.update(verification_status=VerificationStatus.DISPUTED, resolved_at=None)
        self.message_user(request, f"{updated} report(s) marked disputed.")
