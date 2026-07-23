import os
import tempfile
import unittest
import uuid
from unittest import mock

os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="bcsfe-web-test-"))

from bcsfe import core
from bcsfe.cli.feature_handler import FeatureHandler
from bcsfe.webui.app import create_app, _get_session_save, _save_session_save
from bcsfe.webui.feature_coverage import CLI_WEB_FEATURES


def _feature_paths(features, prefix=()):
    for name, value in features.items():
        path = prefix + (str(name),)
        if isinstance(value, dict):
            yield from _feature_paths(value, path)
        else:
            yield "/".join(path)


class WebUICoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def setUp(self):
        self.save_id = str(uuid.uuid4())
        save = core.SaveFile(cc=core.CountryCode("en"), gv=core.GameVersion(140400))
        save.cats.storage_items = [core.StorageItem.init() for _ in range(8)]
        _save_session_save(self.save_id, save)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["save_id"] = self.save_id

    def test_every_cli_feature_has_a_live_web_endpoint(self):
        cli_paths = set(_feature_paths(FeatureHandler(None).get_features()))
        self.assertEqual(cli_paths, set(CLI_WEB_FEATURES))
        endpoints = {rule.endpoint for rule in self.app.url_map.iter_rules()}
        missing = {
            feature: endpoint
            for feature, endpoint in CLI_WEB_FEATURES.items()
            if endpoint not in endpoints
        }
        self.assertEqual({}, missing)

    def test_edits_are_silently_persisted_to_session_save(self):
        operations = (
            ("/edit/item", {"field": "xp", "value": "12345"}),
            ("/edit/storage", {
                "storage_action": "add", "item_type": "1", "item_id": "7", "quantity": "2"
            }),
            ("/edit/other", {"other_action": "medals", "medal_id": "3", "mode": "add"}),
            ("/edit/other", {"other_action": "missions", "mission_id": "12", "state": "2"}),
            ("/edit/other", {"other_action": "talent_orbs", "orb_id": "4", "value": "9"}),
            ("/edit/other", {
                "other_action": "playtime", "hours": "1", "minutes": "2", "seconds": "3"
            }),
            ("/edit/other", {"other_action": "scheme_items", "scheme_id": "5", "mode": "add"}),
            ("/edit/fix", {"fix_action": "unlock_equip"}),
        )
        for url, data in operations:
            self.assertEqual(302, self.client.post(url, data=data).status_code)

        save = _get_session_save(self.save_id)
        self.assertIsNotNone(save)
        self.assertEqual(12345, save.xp)
        self.assertEqual(2, sum(i.item_type == 1 and i.item_id == 7 for i in save.cats.storage_items))
        self.assertTrue(save.medals.has_medal(3))
        self.assertEqual(2, save.missions.clear_states[12])
        self.assertEqual(9, save.talent_orbs.orbs[4].value)
        self.assertEqual((1 * 3600 + 2 * 60 + 3) * 30, save.officer_pass.play_time)
        self.assertIn(5, save.scheme_items.to_obtain)
        self.assertGreaterEqual(save.menu_unlocks[2], 1)

    def test_server_upload_forces_save_even_when_upload_fails(self):
        class FakeServerHandler:
            def __init__(self, save):
                self.save = save

            def get_codes(self):
                self.save.inquiry_code = "FORCED-SAVE"
                return None

        with mock.patch(
            "bcsfe.core.server.server_handler.ServerHandler", FakeServerHandler
        ):
            self.assertEqual(302, self.client.post("/save_upload").status_code)

        save = _get_session_save(self.save_id)
        self.assertEqual("FORCED-SAVE", save.inquiry_code)

    def test_all_local_cli_actions_execute_without_terminal_input(self):
        actions = []
        actions.extend(("/edit/item", {"field": field, "value": "1"}) for field in (
            "catfood", "xp", "normal_tickets", "rare_tickets", "platinum_tickets",
            "legend_tickets", "platinum_shards", "np", "leadership",
            "hundred_million_tickets", "unlocked_slots", "golden_cpu",
        ))
        actions.extend(("/edit/cats", {"cat_action": action}) for action in (
            "unlock_all", "max_upgrade", "true_form_all", "force_true_form_all",
            "remove_true_forms", "fourth_form_all", "force_fourth_form_all",
            "remove_fourth_forms", "remove_talents", "unlock_cat_guide",
            "remove_cat_guide", "reset_levels", "lock_all", "unlock_obtainable",
            "unlock_unobtainable",
        ))
        actions.extend(("/edit/map", {"map_action": action}) for action in (
            "clear_tutorial", "clear_story", "max_treasures", "max_outbreaks",
            "max_aku", "max_uncanny", "max_zero_legends", "max_towers",
            "max_legend_quest", "max_gauntlets", "max_event", "max_sol",
            "max_collab", "unlock_aku_realm", "max_enigma", "challenge_score",
            "dojo_score", "itf_timed_scores", "catamin_stages", "behemoth_culling",
            "collab_gauntlets", "filibuster", "catclaw",
        ))
        actions.extend(("/edit/gamatoto", {"gamatoto_action": action}) for action in (
            "engineers", "base_materials", "ototo_cannon",
        ))
        actions.extend(("/edit/fix", {"fix_action": action}) for action in (
            "fix_gamatoto", "fix_ototo", "fix_time", "fix_officer_pass", "unlock_equip",
        ))
        actions.extend([
            ("/edit/other", {"other_action": "reset_gambling"}),
            ("/edit/other", {"other_action": "restart_pack"}),
            ("/edit/other", {"other_action": "playtime", "hours": "1", "minutes": "2", "seconds": "3"}),
            ("/edit/other", {"other_action": "enemy_guide"}),
            ("/edit/other", {"other_action": "user_rank_rewards"}),
            ("/edit/other", {"other_action": "gold_pass"}),
            ("/edit/other", {"other_action": "medals", "medal_id": "1"}),
            ("/edit/other", {"other_action": "missions", "mission_id": "1", "state": "2"}),
            ("/edit/other", {"other_action": "talent_orbs", "orb_id": "1", "value": "1"}),
            ("/edit/other", {"other_action": "scheme_items", "scheme_id": "1", "mode": "add"}),
        ])
        actions.extend(("/edit/seed", {"seed_field": field, "value": "1"}) for field in (
            "rare_gatya_seed", "normal_gatya_seed", "event_gatya_seed",
        ))

        for url, data in actions:
            with self.subTest(url=url, data=data):
                save_id = str(uuid.uuid4())
                save = core.SaveFile(cc=core.CountryCode("en"), gv=core.GameVersion(140400))
                save.cats.storage_items = [core.StorageItem.init() for _ in range(128)]
                _save_session_save(save_id, save)
                client = self.app.test_client()
                with client.session_transaction() as session:
                    session["save_id"] = save_id
                with mock.patch("builtins.input", side_effect=AssertionError("terminal input used")):
                    self.assertEqual(302, client.post(url, data=data).status_code)
                with client.session_transaction() as session:
                    messages = [message for _, message in session.get("_flashes", [])]
                self.assertFalse(
                    [message for message in messages if message.startswith(("Error:", "Unknown"))],
                    messages,
                )


if __name__ == "__main__":
    unittest.main()
