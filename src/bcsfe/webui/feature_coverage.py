"""Declared WebUI coverage for every leaf in ``FeatureHandler``.

The values are endpoint names used by the WebUI.  Keeping this list explicit
turns newly-added CLI features into a failing test instead of a silent WebUI
regression.
"""

CLI_WEB_FEATURES: dict[str, str] = {
    **{f"save_management/{name}": endpoint for name, endpoint in {
        "save_save": "download_save", "save_upload": "save_upload",
        "save_save_file": "download_save", "save_save_documents": "download_save",
        "adb_push": "device_push", "adb_push_rerun": "device_push",
        "root_push": "device_push", "root_push_rerun": "device_push",
        "export_save": "export_json", "load_save": "load_save",
        "convert_region": "convert_region", "convert_version": "convert_version",
    }.items()},
    **{f"items/{name}": endpoint for name, endpoint in {
        "catfood": "edit_item", "xp": "edit_item", "normal_tickets": "edit_item",
        "rare_tickets": "edit_item", "rare_ticket_trade_feature_name": "rare_ticket_trade",
        "platinum_tickets": "edit_item", "legend_tickets": "edit_item",
        "platinum_shards": "edit_item", "np": "edit_item", "leadership": "edit_item",
        "battle_items": "edit_item", "battle_items_endless": "battle_items_endless",
        "catseyes": "edit_item", "catfruit": "edit_item", "talent_orbs": "edit_other",
        "catamins": "edit_item", "scheme_items": "edit_other",
        "labyrinth_medals": "edit_advanced_item", "100_million_tickets": "edit_item",
        "event_tickets": "edit_advanced_item", "treasure_chests": "edit_advanced_item",
        "reset_golden_cat_cpus": "edit_item",
    }.items()},
    **{f"cats_special_skills/{name}": endpoint for name, endpoint in {
        "unlock_remove_cats": "edit_cats", "upgrade_cats": "edit_cats",
        "true_form_remove_form_cats": "edit_cats", "force_true_form_cats": "edit_cats",
        "fourth_form_remove_form_cats": "edit_cats", "force_fourth_form_cats": "edit_cats",
        "upgrade_talents_remove_talents_cats": "edit_cats",
        "unlock_remove_cat_guide": "edit_cats", "special_skills": "edit_special_skills",
        "cat_storage": "edit_storage",
    }.items()},
    **{f"levels/{name}": "edit_map" for name in (
        "clear_tutorial", "clear_story", "challenge_score", "dojo_score",
        "add_enigma_stages", "clear_enigma_stages", "unlock_aku_realm",
        "story_treasures", "outbreaks", "aku_chapters", "itf_timed_scores",
        "filibuster_reclearing", "sol", "event", "collab", "gauntlets",
        "collab_gauntlets", "uncanny", "catamin_stages", "behemoth_culling",
        "legend_quest", "towers", "zero_legends", "dojo_catclaw_championships",
    )},
    **{f"gamototo/{name}": "edit_gamatoto" for name in (
        "engineers", "base_materials", "gamatoto_xp_level", "gamatoto_helpers",
        "ototo_cat_cannon", "cat_shrine",
    )},
    **{f"account/{name}": "edit_account" for name in (
        "unban_account", "upload_items", "inquiry_code", "password_refresh_token",
    )},
    **{f"gatya/{name}": "edit_seed" for name in (
        "rare_gatya_seed", "normal_gatya_seed", "event_gatya_seed",
    )},
    **{f"fixes/{name}": "edit_fix" for name in (
        "fix_gamatoto_crash", "fix_ototo_crash", "fix_time_errors",
        "unlock_equip_menu", "fix_officer_pass_crash",
    )},
    **{f"other/{name}": endpoint for name, endpoint in {
        "unlocked_slots": "edit_item", "reset_gambling_events": "edit_other",
        "restart_pack": "edit_other", "special_skills": "edit_other",
        "playtime": "edit_other", "enemy_guide": "edit_other",
        "user_rank_rewards": "edit_other", "unlock_equip_menu": "edit_fix",
        "gold_pass": "edit_other", "medals": "edit_other", "missions": "edit_other",
    }.items()},
    "editor/config": "edit_config",
    "editor/update_external": "update_external_content",
    "editor/manage_game_data": "manage_game_data",
    "exit": "unload_save",
}
