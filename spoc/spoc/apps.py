from django.apps import AppConfig


class SpocConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'spoc.spoc'
    label = 'spoc'

    def ready(self):
        import spoc.spoc.signals  # noqa
