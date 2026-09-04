from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from accounts.models import Role, JuryProfile
from events.models import Hackathon, ProblemStatement, JuryTeam, RoundJuryConfig, RoundMarkingParameter
from features.models import Team, TeamEvaluationAssignment
from features.views import sync_automatic_team_assignments
from jury.models import TeamEvaluation

class AlterRoundAssignmentsTests(TestCase):
    def setUp(self):
        # Create Super Admin Role & User
        self.role = Role.objects.create(name='Super Admin')
        self.user = get_user_model().objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='password123',
            role=self.role
        )
        # Create Hackathon
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=2,
            current_jury_round=1
        )
        # Create Problem Statement
        self.ps = ProblemStatement.objects.create(
            hackathon=self.hackathon,
            title='Test Problem Statement',
            domain='Technology'
        )
        # Create student Teams
        self.team1 = Team.objects.create(
            team_name='Team One',
            hackathon=self.hackathon,
            problem_statement=self.ps,
            team_leader=self.user,
            current_round=1
        )
        self.team2 = Team.objects.create(
            team_name='Team Two',
            hackathon=self.hackathon,
            problem_statement=self.ps,
            team_leader=self.user,
            current_round=1
        )
        # Create two panels for this problem statement
        self.panel_a = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Panel A',
            display_order=1,
            problem_statement=self.ps
        )
        self.panel_b = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Panel B',
            display_order=2,
            problem_statement=self.ps
        )

    def test_sync_automatic_team_assignments_standard_order(self):
        # By default, alter_assignment is False (or no config exists)
        sync_automatic_team_assignments(self.hackathon, round_number=1)

        # Team 1 (first) should be in Panel A (display_order 1)
        # Team 2 (second) should be in Panel B (display_order 2)
        assign1 = TeamEvaluationAssignment.objects.get(team=self.team1, round_number=1)
        assign2 = TeamEvaluationAssignment.objects.get(team=self.team2, round_number=1)

        self.assertEqual(assign1.assigned_panel, self.panel_a)
        self.assertEqual(assign2.assigned_panel, self.panel_b)

    def test_sync_automatic_team_assignments_altered_order(self):
        # Create a RoundJuryConfig with alter_offset=1
        RoundJuryConfig.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            alter_offset=1
        )

        sync_automatic_team_assignments(self.hackathon, round_number=1)

        # Shift offset=1 rotates panel A & B. So B becomes first and A becomes second.
        assign1 = TeamEvaluationAssignment.objects.get(team=self.team1, round_number=1)
        assign2 = TeamEvaluationAssignment.objects.get(team=self.team2, round_number=1)

        self.assertEqual(assign1.assigned_panel, self.panel_b)
        self.assertEqual(assign2.assigned_panel, self.panel_a)

    def test_sync_automatic_team_assignments_multiple_shifts(self):
        # Create Panel C
        panel_c = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Panel C',
            display_order=3,
            problem_statement=self.ps
        )
        # Create Team Three
        team3 = Team.objects.create(
            team_name='Team Three',
            hackathon=self.hackathon,
            problem_statement=self.ps,
            team_leader=self.user,
            current_round=1
        )

        config = RoundJuryConfig.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            alter_offset=1
        )

        # Offset 1: Shift by 1 -> Panel B, Panel C, Panel A
        sync_automatic_team_assignments(self.hackathon, round_number=1)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=self.team1).assigned_panel, self.panel_b)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=self.team2).assigned_panel, panel_c)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=team3).assigned_panel, self.panel_a)

        # Offset 2: Shift by 2 -> Panel C, Panel A, Panel B
        config.alter_offset = 2
        config.save()
        sync_automatic_team_assignments(self.hackathon, round_number=1)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=self.team1).assigned_panel, panel_c)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=self.team2).assigned_panel, self.panel_a)
        self.assertEqual(TeamEvaluationAssignment.objects.get(team=team3).assigned_panel, self.panel_b)

    def test_alter_round_assignments_view(self):
        self.client.force_login(self.user)
        
        # Initially, check no config exists or alter_offset is 0
        config = RoundJuryConfig.objects.filter(hackathon=self.hackathon, round_number=1).first()
        self.assertTrue(config is None or config.alter_offset == 0)

        # Call the view to alter assignments once (increments to 1)
        response = self.client.post(reverse('alter_round_assignments'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1
        })

        # Should redirect back to evaluation with show_assignments=true
        expected_redirect = f'/features/jury/?sub=evaluation&hackathon={self.hackathon.id}&round_number=1&show_assignments=true'
        self.assertRedirects(response, expected_redirect)

        # Verify RoundJuryConfig now has alter_offset=1 and alter_assignment=True
        config = RoundJuryConfig.objects.get(hackathon=self.hackathon, round_number=1)
        self.assertEqual(config.alter_offset, 1)
        self.assertTrue(config.alter_assignment)

        # Call the view again (increments to 2)
        response2 = self.client.post(reverse('alter_round_assignments'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1
        })
        self.assertRedirects(response2, expected_redirect)
        config.refresh_from_db()
        self.assertEqual(config.alter_offset, 2)

        # Call the view with reset=true to restore standard order
        response_reset = self.client.post(reverse('alter_round_assignments'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1,
            'reset': 'true'
        })
        self.assertRedirects(response_reset, expected_redirect)

        config.refresh_from_db()
        self.assertEqual(config.alter_offset, 0)
        self.assertFalse(config.alter_assignment)


class ResultsAndRoundPromotionTests(TestCase):
    def setUp(self):
        # Create Super Admin Role & User
        self.role = Role.objects.create(name='Super Admin')
        self.user = get_user_model().objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='password123',
            role=self.role
        )
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=1,
            current_jury_round=1
        )
        # Create marking parameters
        self.param1 = RoundMarkingParameter.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Parameter 1',
            cutoff_score=50.0
        )
        self.param2 = RoundMarkingParameter.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Parameter 2',
            cutoff_score=60.0
        )
        
        # Create multiple teams (e.g., 12 teams) to verify top 10 slice
        self.teams = []
        for i in range(1, 13):
            t = Team.objects.create(
                team_name=f'Team {i}',
                hackathon=self.hackathon,
                team_leader=self.user,
                current_round=1
            )
            self.teams.append(t)
            
            # Add evaluations for each team. Let's make Team i overall score be related to i.
            # E.g. Team 1 gets lower score, Team 12 gets highest score.
            # Team i gets: param1 = 40 + i, param2 = 50 + i
            # Overall score = ((40+i) + (50+i)) / 2 = 45 + i
            # For Team 12: overall score is 57
            # For Team 1: overall score is 46 (which is less than cutoff score 50 and 60, so unqualified!)
            score1 = 40 + i
            score2 = 50 + i
            TeamEvaluation.objects.create(
                team=t,
                round_number=1,
                evaluator=self.user,
                parameter=self.param1,
                score=score1,
                remarks="Good"
            )
            TeamEvaluation.objects.create(
                team=t,
                round_number=1,
                evaluator=self.user,
                parameter=self.param2,
                score=score2,
                remarks="Good"
            )

    def test_results_reporting_top_10_filter(self):
        self.client.force_login(self.user)
        # Request page with top_10=true
        response = self.client.get(reverse('results_reporting_management'), {
            'hackathon': self.hackathon.id,
            'round': 1,
            'top_10': 'true'
        })
        self.assertEqual(response.status_code, 200)
        teams_data = response.context['teams_data']
        
        # Should return exactly 10 teams
        self.assertEqual(len(teams_data), 10)
        
        # The returned teams should be sorted in descending order by overall_score
        # Best overall score should be first: Team 12 (overall score: 45 + 12 = 57)
        self.assertEqual(teams_data[0]['team'].team_name, 'Team 12')
        self.assertEqual(teams_data[9]['team'].team_name, 'Team 3')

    def test_save_cutoffs_calculates_and_shows_qualified_count(self):
        self.client.force_login(self.user)
        
        # Let's save cutoffs: Param1=50, Param2=60
        # Let's check which teams are qualified:
        # Team i gets: param1 score = 40+i, param2 score = 50+i
        # To qualify, 40+i >= 50 (so i >= 10) AND 50+i >= 60 (so i >= 10).
        # So only Team 10, Team 11, Team 12 are qualified (3 teams!).
        response = self.client.post(
            reverse('results_reporting_management') + f'?hackathon={self.hackathon.id}&round=1', 
            {
                'action': 'save_cutoffs',
                f'cutoff_{self.param1.id}': '50.00',
                f'cutoff_{self.param2.id}': '60.00'
            }
        )
        
        # Should redirect back to evaluation view
        self.assertEqual(response.status_code, 302)
        
        # Follow the redirect and verify success message containing the qualified count
        redirect_response = self.client.get(response.url)
        messages = list(redirect_response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn("Currently, 3 teams are qualified", str(messages[0]))
        
        # Verify context counts
        self.assertEqual(redirect_response.context['qualified_teams_count'], 3)
        self.assertEqual(redirect_response.context['total_teams_count'], 12)


class JuryPanelPreserveOnSaveTests(TestCase):
    def setUp(self):
        # Create Super Admin Role & User
        self.role = Role.objects.create(name='Super Admin')
        self.user = get_user_model().objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='password123',
            role=self.role
        )
        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=1,
            current_jury_round=1
        )
        self.ps1 = ProblemStatement.objects.create(
            hackathon=self.hackathon,
            title='PS One',
            domain='Web'
        )
        self.ps2 = ProblemStatement.objects.create(
            hackathon=self.hackathon,
            title='PS Two',
            domain='App'
        )
        self.panel_a = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Panel A',
            problem_statement=self.ps1
        )
        self.panel_b = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Panel B',
            problem_statement=self.ps2
        )

    def test_save_all_jury_panels_preserves_unsubmitted_panels(self):
        self.client.force_login(self.user)
        
        # Post to save_all_jury_panels with only Panel A's data (simulating PS filter active)
        # Note: panel_b's keys are completely omitted!
        response = self.client.post(reverse('save_all_jury_panels'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1,
            f'panel_{self.panel_a.id}_problem_statement_id': self.ps2.id,  # changing panel A to PS 2
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify Panel A was updated
        self.panel_a.refresh_from_db()
        self.assertEqual(self.panel_a.problem_statement, self.ps2)
        
        # Verify Panel B remains untouched (retains self.ps2 and is NOT erased to None)
        self.panel_b.refresh_from_db()
        self.assertEqual(self.panel_b.problem_statement, self.ps2)


class JuryDashboardVerificationTests(TestCase):
    def setUp(self):
        # Create Super Admin User for setup
        self.role_admin = Role.objects.create(name='Super Admin')
        self.admin = get_user_model().objects.create_user(
            username='admin_user',
            email='admin@example.com',
            password='password123',
            role=self.role_admin
        )
        # Create Jury User
        self.role_jury = Role.objects.create(name='Jury')
        self.jury_user = get_user_model().objects.create_user(
            username='jury_member',
            email='jury@example.com',
            password='password123',
            role=self.role_jury
        )
        self.jury_profile = JuryProfile.objects.create(
            user=self.jury_user,
            domain='Web'
        )

        self.hackathon = Hackathon.objects.create(
            name='Test Hackathon',
            organization_name='Test Org',
            number_of_rounds=1,
            current_jury_round=1
        )
        self.ps = ProblemStatement.objects.create(
            hackathon=self.hackathon,
            title='PS Web development',
            domain='Web'
        )
        # Create student team
        self.team = Team.objects.create(
            team_name='Web Wizards',
            hackathon=self.hackathon,
            problem_statement=self.ps,
            team_leader=self.admin,
            current_round=1
        )

        # Create JuryTeam panel and assign the jury profile
        self.panel = JuryTeam.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Web Panel',
            problem_statement=self.ps
        )
        self.panel.juries.add(self.jury_profile)

        # Sync automatic assignments to map Web Wizards team to Web Panel (and hence to jury_member)
        sync_automatic_team_assignments(self.hackathon, round_number=1)

    def test_assigned_team_shows_on_jury_dashboard(self):
        # Log in as the jury member
        self.client.force_login(self.jury_user)

        # Request the jury dashboard
        response = self.client.get(reverse('jury_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Assert that the assigned team "Web Wizards" is in the context
        team_cards = response.context['team_cards']
        self.assertEqual(len(team_cards), 1)
        self.assertEqual(team_cards[0]['team_name'], 'Web Wizards')

        # Request the team evaluations list page
        response_evals = self.client.get(reverse('jury_team_evaluations'))
        self.assertEqual(response_evals.status_code, 200)
        self.assertEqual(len(response_evals.context['team_cards']), 1)
        self.assertEqual(response_evals.context['team_cards'][0]['team_name'], 'Web Wizards')

        # Request the team detail page
        response_detail = self.client.get(reverse('jury_team_detail', kwargs={'team_id': self.team.id}))
        self.assertEqual(response_detail.status_code, 200)
        self.assertEqual(response_detail.context['team'].team_name, 'Web Wizards')

    def test_assign_round_teams_and_score_validation(self):
        # 1. Test assign_round_teams POST view
        self.client.force_login(self.admin)
        response_assign = self.client.post(reverse('assign_round_teams'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1
        })
        self.assertEqual(response_assign.status_code, 302)
        
        # Check has_assigned_teams flag
        from events.models import RoundJuryConfig
        config = RoundJuryConfig.objects.get(hackathon=self.hackathon, round_number=1)
        self.assertTrue(config.has_assigned_teams)

        # 2. Test param.max_marks validation in jury_submit_marks
        # Create a parameter with max_marks=18.00 and cutoff_score=15.00 (team promotion cutoff)
        param = RoundMarkingParameter.objects.create(
            hackathon=self.hackathon,
            round_number=1,
            name='Presentation',
            max_marks=18.00,
            cutoff_score=15.00
        )

        self.client.force_login(self.jury_user)
        # Submit a score of 19 (exceeds max_marks 18.00) -> should be rejected/skipped
        response_submit_invalid = self.client.post(reverse('jury_submit_marks', kwargs={'team_id': self.team.id}), {
            f'score_{param.id}': '19.0',
            'round_number': 1
        })
        self.assertEqual(response_submit_invalid.status_code, 302)
        self.assertFalse(TeamEvaluation.objects.filter(team=self.team, parameter=param).exists())

        # Submit a score of 17 (under max_marks 18.00) -> should save successfully
        response_submit_valid = self.client.post(reverse('jury_submit_marks', kwargs={'team_id': self.team.id}), {
            f'score_{param.id}': '17.0',
            'round_number': 1
        })
        self.assertEqual(response_submit_valid.status_code, 302)
        self.assertTrue(TeamEvaluation.objects.filter(team=self.team, parameter=param, score=17.0).exists())

        # 3. Test that panel modifications reset has_assigned_teams to False
        self.client.force_login(self.admin)
        
        # Test add_jury_panel resets it
        config.has_assigned_teams = True
        config.save()
        self.client.post(reverse('add_jury_panel'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1,
            'panel_name': 'New Panel Test'
        })
        config.refresh_from_db()
        self.assertFalse(config.has_assigned_teams)

        # Test delete_jury_panel resets it
        config.has_assigned_teams = True
        config.save()
        new_panel = JuryTeam.objects.get(name='New Panel Test')
        self.client.post(reverse('delete_jury_panel', kwargs={'panel_id': new_panel.id}))
        config.refresh_from_db()
        self.assertFalse(config.has_assigned_teams)

        # Test save_all_jury_panels resets it
        config.has_assigned_teams = True
        config.save()
        self.client.post(reverse('save_all_jury_panels'), {
            'hackathon_id': self.hackathon.id,
            'round_number': 1,
            f'panel_{self.panel.id}_problem_statement_id': self.ps.id
        })
        config.refresh_from_db()
        self.assertFalse(config.has_assigned_teams)
