from django.apps import AppConfig
class TeamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'team.team'
    label = 'team'
    def ready(self):
        import team.team.signals  # noqa
