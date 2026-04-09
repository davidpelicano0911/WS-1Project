from django.conf import settings
from django.db import models
from django.urls import reverse


class DataSuggestion(models.Model):
    ENTITY_PLAYER = "player"
    ENTITY_TEAM = "team"
    ENTITY_CHOICES = [
        (ENTITY_PLAYER, "Player"),
        (ENTITY_TEAM, "Team"),
    ]

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    entity_type = models.CharField(max_length=16, choices=ENTITY_CHOICES)
    entity_id = models.CharField(max_length=64)
    entity_year = models.PositiveIntegerField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_suggestions",
    )
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_data_suggestions",
    )
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        suffix = f" ({self.entity_year})" if self.entity_year else ""
        return f"{self.get_entity_type_display()} · {self.entity_id}{suffix} · {self.get_status_display()}"

    @property
    def entity_url(self):
        if self.entity_type == self.ENTITY_PLAYER:
            return reverse("player_detail", args=[self.entity_id])
        if self.entity_type == self.ENTITY_TEAM:
            base_url = reverse("team_detail", args=[self.entity_id])
            if self.entity_year:
                return f"{base_url}?year={self.entity_year}"
            return base_url
        return "#"


class DataSuggestionChange(models.Model):
    suggestion = models.ForeignKey(
        DataSuggestion,
        on_delete=models.CASCADE,
        related_name="changes",
    )
    field_key = models.CharField(max_length=64)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.suggestion_id} · {self.field_key}"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    score = models.PositiveSmallIntegerField()
    total_questions = models.PositiveSmallIntegerField(default=10)
    percentage = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-percentage", "-completed_at"]

    def __str__(self):
        return f"{self.user} · {self.score}/{self.total_questions}"
