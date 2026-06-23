from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetView


class HackathonPasswordResetForm(PasswordResetForm):
    def save(
        self,
        domain_override=None,
        subject_template_name='registration/password_reset_subject.txt',
        email_template_name='registration/password_reset_email.html',
        use_https=False,
        token_generator=None,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        effective_from_email = (
            from_email
            or settings.EMAIL_HOST_USER
            or settings.DEFAULT_FROM_EMAIL
        )
        return super().save(
            domain_override=domain_override,
            subject_template_name=subject_template_name,
            email_template_name=email_template_name,
            use_https=use_https,
            token_generator=token_generator,
            from_email=effective_from_email,
            request=request,
            html_email_template_name=html_email_template_name,
            extra_email_context=extra_email_context,
        )


class HackathonPasswordResetView(PasswordResetView):
    form_class = HackathonPasswordResetForm
    from_email = settings.EMAIL_HOST_USER or settings.DEFAULT_FROM_EMAIL
