from django.conf import settings
from django.db import models


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
