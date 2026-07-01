from __future__ import annotations

"""Flask web application for BCSFE."""

import os
import io
import uuid
import tempfile
import traceback
from pathlib import Path as SysPath
from typing import Any

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    send_file,
    flash,
    session,
    jsonify,
)

from bcsfe import core
from bcsfe.core.country_code import CountryCode
from bcsfe.core.io.config import ConfigKey
from bcsfe.core.io.save import SaveFile, SaveError
from bcsfe.core.io.data import Data
from bcsfe.core.io.path import Path as BcPath
from bcsfe.core.game.catbase.gambling import GamblingEvent
from bcsfe.core.game.catbase.officer_pass import OfficerPass
from bcsfe.core.game.catbase.playtime import PlayTime
from bcsfe.core.game.catbase.medals import Medals
from bcsfe.core.game.catbase.mission import Missions
from bcsfe.core.game.catbase.talent_orbs import SaveOrbs
from bcsfe.core.game.map.story import StoryChapters
from bcsfe.core.server.server_handler import ServerHandler
from bcsfe.cli.edits.basic_items import BasicItems
from bcsfe.cli.edits.fixes import Fixes
from bcsfe.cli.edits.clear_tutorial import clear_tutorial
from bcsfe.cli.edits.event_tickets import EventTickets
from bcsfe.cli.edits.aku_realm import unlock_aku_realm
from bcsfe.cli.edits.rare_ticket_trade import RareTicketTrade
from bcsfe.webui.lang import get_translator
from bcsfe.webui import edits as web_edits

BFCSaveFile = SaveFile

TEMP_DIR = SysPath(tempfile.gettempdir()) / "bcsfe_webui"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_DESCRIPTIONS: dict[ConfigKey, tuple[str, str]] = {
    ConfigKey.UPDATE_TO_BETA: ("Update to beta versions", "boolean"),
    ConfigKey.SHOW_UPDATE_MESSAGE: ("Show update message on start", "boolean"),
    ConfigKey.LOCALE: ("Locale (en, tw, vi)", "string"),
    ConfigKey.SHOW_MISSING_LOCALE_KEYS: ("Show missing locale keys", "boolean"),
    ConfigKey.DISABLE_MAXES: ("Disable max values for editing", "boolean"),
    ConfigKey.MAX_BACKUPS: ("Maximum number of backups", "int"),
    ConfigKey.THEME: ("Theme name", "string"),
    ConfigKey.RESET_CAT_DATA: ("Reset cat data on edit", "boolean"),
    ConfigKey.SET_CAT_CURRENT_FORMS: ("Set cat current forms", "boolean"),
    ConfigKey.STRICT_UPGRADE: ("Strict upgrade mode", "boolean"),
    ConfigKey.SEPARATE_CAT_EDIT_OPTIONS: ("Separate cat edit options", "boolean"),
    ConfigKey.STRICT_BAN_PREVENTION: ("Strict ban prevention", "boolean"),
    ConfigKey.MAX_REQUEST_TIMEOUT: ("Max request timeout (seconds)", "int"),
    ConfigKey.GAME_DATA_REPO: ("Game data repository URL", "string"),
    ConfigKey.FORCE_LANG_GAME_DATA: ("Force language for game data", "boolean"),
    ConfigKey.CLEAR_TUTORIAL_ON_LOAD: ("Clear tutorial on load", "boolean"),
    ConfigKey.REMOVE_BAN_MESSAGE_ON_LOAD: ("Remove ban message on load", "boolean"),
    ConfigKey.UNLOCK_CAT_ON_EDIT: ("Unlock cat on edit", "boolean"),
    ConfigKey.USE_FILE_DIALOG: ("Use file dialog", "boolean"),
    ConfigKey.ADB_PATH: ("ADB path", "string"),
    ConfigKey.IGNORE_PARSE_ERROR: ("Ignore parse error", "boolean"),
    ConfigKey.USE_PKEXEC_WAYDROID: ("Use pkexec for Waydroid", "boolean"),
}


def create_app() -> Flask:
    core.core_data.init_data()

    app = Flask(
        __name__,
        template_folder=str(SysPath(__file__).parent / "templates"),
        static_folder=str(SysPath(__file__).parent / "static"),
    )
    app.secret_key = os.environ.get("BCSFE_WEB_SECRET", "bcsfe-web-default-key-change-me")

    @app.context_processor
    def inject_globals():
        ui_lang = session.get("ui_lang", "en")
        t = get_translator(ui_lang)
        return {
            "t": t,
            "ui_lang": ui_lang,
            "last_transfer_code": session.get("last_transfer_code", ""),
            "last_confirmation_code": session.get("last_confirmation_code", ""),
        }

    _register_routes(app)
    _register_filters(app)
    return app


def _get_temp_path(session_id: str) -> BcPath:
    return BcPath(str(TEMP_DIR / f"{session_id}.save"))


def _get_session_save(session_id: str | None) -> BFCSaveFile | None:
    if not session_id:
        return None
    temp_path = _get_temp_path(session_id)
    if not temp_path.exists():
        return None
    try:
        data = temp_path.read()
        return BFCSaveFile(data)
    except (SaveError, Exception):
        return None


def _save_session_save(session_id: str, sf: BFCSaveFile):
    temp_path = _get_temp_path(session_id)
    sf.to_file(temp_path)


def _clear_session_save(session_id: str):
    temp_path = _get_temp_path(session_id)
    if temp_path.exists():
        temp_path.remove()


def _get_gatya_names(sf: BFCSaveFile):
    return core.core_data.get_gatya_item_names(sf)


def _get_gatya_buy(sf: BFCSaveFile):
    return core.core_data.get_gatya_item_buy(sf)


def _safe_int(value: str | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _register_filters(app: Flask):
    @app.template_filter("iso_datetime")
    def iso_datetime_filter(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)


def _register_routes(app: Flask):
    _register_save_routes(app)
    _register_item_routes(app)
    _register_cat_routes(app)
    _register_map_routes(app)
    _register_gamatoto_routes(app)
    _register_account_routes(app)
    _register_fix_routes(app)
    _register_other_routes(app)
    _register_seed_routes(app)
    _register_config_routes(app)


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------
def _register_save_routes(app: Flask):
    @app.route("/", methods=["GET"])
    def index():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        save_info = None
        if sf is not None:
            inquiry = sf.inquiry_code or ""
            save_info = {
                "inquiry_code": inquiry[:4] + "***" + inquiry[-2:] if len(inquiry) > 6 else inquiry,
                "game_version": str(sf.game_version) if sf.game_version else "?",
                "cc": str(sf.cc) if sf.cc else "?",
                "catfood": sf.catfood,
                "xp": sf.xp,
                "normal_tickets": sf.normal_tickets,
                "rare_tickets": sf.rare_tickets,
                "catfood_max": core.core_data.max_value_manager.catfood,
                "xp_max": core.core_data.max_value_manager.xp,
                "normal_tickets_max": core.core_data.max_value_manager.normal_tickets,
                "rare_tickets_max": core.core_data.max_value_manager.rare_tickets,
                "platinum_tickets": sf.platinum_tickets,
                "legend_tickets": sf.legend_tickets,
                "platinum_shards": sf.platinum_shards,
                "np": sf.np,
                "leadership": sf.leadership,
                "hundred_million_tickets": sf.hundred_million_ticket,
            }
            # catseyes: get names & current values
            names_o = _get_gatya_names(sf)
            items = _get_gatya_buy(sf)
            catseyes_items = items.get_by_category(5) if items else None
            catseyes_list: list[dict] = []
            if catseyes_items:
                values = sf.catseyes
                for i, item in enumerate(catseyes_items):
                    name = names_o.get_name(item.id) or f"Catseye {item.id}"
                    cur_val = values[i] if i < len(values) else 0
                    catseyes_list.append({"name": name, "value": cur_val, "idx": i})
            save_info["catseyes"] = catseyes_list

            catfruit_items = items.get_by_category(0) if items else None
            catfruit_list: list[dict] = []
            if catfruit_items:
                values = sf.catfruit
                for i, item in enumerate(catfruit_items):
                    name = names_o.get_name(item.id) or f"Catfruit {item.id}"
                    cur_val = values[i] if i < len(values) else 0
                    catfruit_list.append({"name": name, "value": cur_val, "idx": i})
            save_info["catfruit"] = catfruit_list

            catamin_items = items.get_by_category(6) if items else None
            catamin_list: list[dict] = []
            if catamin_items:
                values = sf.catamins
                for i, item in enumerate(catamin_items):
                    name = names_o.get_name(item.id) or f"Catamin {item.id}"
                    cur_val = values[i] if i < len(values) else 0
                    catamin_list.append({"name": name, "value": cur_val, "idx": i})
            save_info["catamins"] = catamin_list

            battle_items = items.get_by_category(1) if items else None
            battle_items_list: list[dict] = []
            if battle_items:
                values = sf.battle_items.items
                for i, item in enumerate(battle_items):
                    name = names_o.get_name(item.id) or f"Battle Item {item.id}"
                    cur_val = values[i] if i < len(values) else 0
                    battle_items_list.append({"name": name, "value": cur_val, "idx": i})
            save_info["battle_items"] = battle_items_list

        return render_template(
            "index.html",
            save_info=save_info,
            config_keys=list(_CONFIG_DESCRIPTIONS.items()),
            config_values={k.value: core.core_data.config.get(k) for k in _CONFIG_DESCRIPTIONS},
        )

    @app.route("/load", methods=["POST"])
    def load_save():
        if "save_file" not in request.files:
            flash("No file uploaded")
            return redirect(url_for("index"))
        file = request.files["save_file"]
        if file.filename == "":
            flash("No file selected")
            return redirect(url_for("index"))
        try:
            raw_bytes = file.read()
            data = Data(raw_bytes)
            sf = BFCSaveFile(data)
            session_id = str(uuid.uuid4())
            session["save_id"] = session_id
            _save_session_save(session_id, sf)
            flash("Save file loaded successfully")
        except SaveError as e:
            flash(f"Failed to load save file: {e}")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))

    @app.route("/unload", methods=["POST"])
    def unload_save():
        session_id = session.pop("save_id", None)
        if session_id:
            _clear_session_save(session_id)
        session.pop("last_transfer_code", None)
        session.pop("last_confirmation_code", None)
        flash("Save file unloaded")
        return redirect(url_for("index"))

    @app.route("/download", methods=["POST"])
    def download_save():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        data = sf.to_data()
        buf = io.BytesIO(data.get_raw() if hasattr(data, "get_raw") else bytes(data))
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name="SAVE_DATA",
        )

    @app.route("/export_json", methods=["POST"])
    def export_json():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            json_data = sf.to_dict()
            import json
            buf = io.BytesIO(json.dumps(json_data, indent=2).encode("utf-8"))
            buf.seek(0)
            return send_file(
                buf,
                mimetype="application/json",
                as_attachment=True,
                download_name="SAVE_DATA.json",
            )
        except Exception as e:
            flash(f"Export failed: {e}")
            return redirect(url_for("index"))

    @app.route("/convert_region", methods=["POST"])
    def convert_region():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        target_cc = request.form.get("target_cc", "en")
        try:
            cc = CountryCode(target_cc)
            sf.set_cc(cc)
            sf.save_path = None
            _save_session_save(session_id, sf)
            flash(f"Region converted to {cc}")
        except Exception as e:
            flash(f"Conversion failed: {e}")
        return redirect(url_for("index"))

    @app.route("/convert_version", methods=["POST"])
    def convert_version():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        target_gv = request.form.get("target_gv", "")
        if not target_gv:
            flash("No version specified")
            return redirect(url_for("index"))
        try:
            from bcsfe.core.game_version import GameVersion
            gv = GameVersion.from_string(target_gv)
            sf.set_gv(gv)
            _save_session_save(session_id, sf)
            flash(f"Version converted to {target_gv}")
        except Exception as e:
            flash(f"Conversion failed: {e}")
        return redirect(url_for("index"))

    @app.route("/save_upload", methods=["POST"])
    def save_upload():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            from bcsfe.core.server.server_handler import ServerHandler
            result = ServerHandler(sf).get_codes()
            if result is not None:
                transfer_code, confirmation_code = result
                session["last_transfer_code"] = transfer_code
                session["last_confirmation_code"] = confirmation_code
                _save_session_save(session_id, sf)
                flash(f"Upload OK")
            else:
                flash("Upload failed - server returned no codes")
        except Exception as e:
            flash(f"Upload error: {e}")
        return redirect(url_for("index"))

    @app.route("/download_from_codes", methods=["POST"])
    def download_from_codes():
        transfer_code = request.form.get("transfer_code", "").strip()
        confirmation_code = request.form.get("confirmation_code", "").strip()
        cc_str = request.form.get("cc", "en")
        if not transfer_code or not confirmation_code:
            flash("Both transfer code and confirmation code are required")
            return redirect(url_for("index"))
        try:
            cc = core.CountryCode(cc_str)
            gv = core.GameVersion(120200)
            from bcsfe.core.server.server_handler import ServerHandler
            server_handler, result = ServerHandler.from_codes(
                transfer_code, confirmation_code, cc, gv,
            )
            if server_handler is None:
                flash("Invalid codes or server error - could not download save")
                return redirect(url_for("index"))
            save_file = server_handler.save_file
            session_id = str(uuid.uuid4())
            session["save_id"] = session_id
            _save_session_save(session_id, save_file)
            flash("Save downloaded from server successfully")
        except Exception as e:
            flash(f"Download failed: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
def _register_item_routes(app: Flask):
    @app.route("/edit/item", methods=["POST"])
    def edit_item():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            return jsonify({"error": "No save loaded"}), 400

        field = request.form.get("field", "")
        value = _safe_int(request.form.get("value"))

        try:
            if field == "catfood":
                sf.catfood = min(value, core.core_data.max_value_manager.catfood)
                from bcsfe.core.server.managed_item import ManagedItem, BackupMetaData, ManagedItemType
                BackupMetaData(sf).add_managed_item(
                    ManagedItem.from_change(sf.catfood - 0, ManagedItemType.CATFOOD)
                )
            elif field == "xp":
                sf.xp = min(value, core.core_data.max_value_manager.xp)
            elif field == "normal_tickets":
                sf.normal_tickets = min(value, core.core_data.max_value_manager.normal_tickets)
            elif field == "rare_tickets":
                sf.rare_tickets = min(value, core.core_data.max_value_manager.rare_tickets)
                from bcsfe.core.server.managed_item import ManagedItem, BackupMetaData, ManagedItemType
                BackupMetaData(sf).add_managed_item(
                    ManagedItem.from_change(sf.rare_tickets - 0, ManagedItemType.RARE_TICKET)
                )
            elif field == "platinum_tickets":
                sf.platinum_tickets = min(value, core.core_data.max_value_manager.platinum_tickets)
                from bcsfe.core.server.managed_item import ManagedItem, BackupMetaData, ManagedItemType
                BackupMetaData(sf).add_managed_item(
                    ManagedItem.from_change(sf.platinum_tickets - 0, ManagedItemType.PLATINUM_TICKET)
                )
            elif field == "legend_tickets":
                sf.legend_tickets = min(value, core.core_data.max_value_manager.legend_tickets)
                from bcsfe.core.server.managed_item import ManagedItem, BackupMetaData, ManagedItemType
                BackupMetaData(sf).add_managed_item(
                    ManagedItem.from_change(sf.legend_tickets - 0, ManagedItemType.LEGEND_TICKET)
                )
            elif field == "platinum_shards":
                sf.platinum_shards = min(value, core.core_data.max_value_manager.platinum_tickets * 10)
            elif field == "np":
                sf.np = min(value, core.core_data.max_value_manager.np)
            elif field == "leadership":
                sf.leadership = min(value, core.core_data.max_value_manager.leadership)
            elif field == "hundred_million_tickets":
                sf.hundred_million_ticket = min(value, core.core_data.max_value_manager.hundred_million_tickets)
            elif field == "unlocked_slots":
                sf.unlocked_slots = value
            elif field == "inquiry_code":
                sf.inquiry_code = request.form.get("value", "")
            elif field.startswith("catseyes_"):
                idx = _safe_int(field.replace("catseyes_", ""))
                vals = list(sf.catseyes)
                while len(vals) <= idx:
                    vals.append(0)
                vals[idx] = value
                sf.catseyes = vals
            elif field.startswith("catfruit_"):
                idx = _safe_int(field.replace("catfruit_", ""))
                vals = list(sf.catfruit)
                while len(vals) <= idx:
                    vals.append(0)
                vals[idx] = value
                sf.catfruit = vals
            elif field.startswith("catamin_"):
                idx = _safe_int(field.replace("catamin_", ""))
                vals = list(sf.catamins)
                while len(vals) <= idx:
                    vals.append(0)
                vals[idx] = value
                sf.catamins = vals
            elif field.startswith("battle_item_"):
                idx = _safe_int(field.replace("battle_item_", ""))
                vals = list(sf.battle_items.items)
                while len(vals) <= idx:
                    vals.append(0)
                vals[idx] = value
                sf.battle_items.items = vals
            elif field == "golden_cpu":
                sf.golden_cpu_count = 0
            else:
                return jsonify({"error": f"Unknown field: {field}"}), 400

            _save_session_save(session_id, sf)
            flash("Value updated")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Error: {e}")
            return redirect(url_for("index"))

    @app.route("/edit/rare_ticket_trade", methods=["POST"])
    def rare_ticket_trade():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            RareTicketTrade.rare_ticket_trade(sf)
            _save_session_save(session_id, sf)
            flash("Rare ticket trade completed")
        except Exception as e:
            flash(f"Trade failed: {e}")
        return redirect(url_for("index"))

    @app.route("/edit/battle_items_endless", methods=["POST"])
    def battle_items_endless():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            sf.battle_items.edit_endless_items(sf)
            _save_session_save(session_id, sf)
            flash("Battle items set to endless")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))

    @app.route("/edit/event_tickets", methods=["POST"])
    def edit_event_tickets():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            EventTickets.edit(sf)
            _save_session_save(session_id, sf)
            flash("Event tickets edited")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Cats
# ---------------------------------------------------------------------------
def _register_cat_routes(app: Flask):
    @app.route("/edit/cats", methods=["POST"])
    def edit_cats():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("cat_action", "")
        try:
            from bcsfe.cli.edits.cat_editor import CatEditor
            ce = CatEditor(sf)
            if action == "unlock_all":
                cats = ce.get_non_unlocked_cats()
                for cat in cats:
                    cat.unlock(sf)
                flash(f"Unlocked {len(cats)} cats")
            elif action == "max_upgrade":
                for cat in sf.cats.cats:
                    if not cat.unlocked:
                        continue
                    cat.upgrade.base = 60
                    cat.upgrade.plus = 90
                flash("All cats upgraded to max")
            elif action == "true_form_all":
                cats = ce.get_current_cats()
                sf.cats.true_form_cats(sf, cats, force=False, set_current_forms=True)
                flash("True forms enabled for all cats")
            elif action == "fourth_form_all":
                cats = ce.get_current_cats()
                sf.cats.fourth_form_cats(sf, cats, force=False, set_current_forms=True)
                flash("Fourth forms enabled for all cats")
            elif action == "max_talents":
                flash("Max talents not available in web UI - use CLI")
            elif action == "unlock_cat_guide":
                for cat in ce.get_current_cats():
                    cat.catguide_collected = True
                flash("Cat guide unlocked for all cats")
            elif action == "unlock_obtainable":
                cats = sf.cats.get_cats_obtainable(sf)
                if cats:
                    for cat in cats:
                        cat.unlock(sf)
                    flash(f"Unlocked {len(cats)} obtainable cats")
            elif action == "unlock_unobtainable":
                cats = sf.cats.get_cats_non_obtainable(sf)
                if cats:
                    for cat in cats:
                        cat.unlock(sf)
                    flash(f"Unlocked {len(cats)} unobtainable cats")
            elif action == "reset_levels":
                count = 0
                for cat in sf.cats.cats:
                    if cat.unlocked:
                        cat.upgrade.base = 0
                        cat.upgrade.plus = 0
                        count += 1
                flash(f"Reset {count} cats to level 1+0")
            elif action == "lock_all":
                count = 0
                for cat in sf.cats.cats:
                    if cat.unlocked:
                        cat.remove(reset=True, save_file=sf)
                        count += 1
                flash(f"Removed {count} cats")
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))

    @app.route("/edit/cat_single", methods=["POST"])
    def edit_cat_single():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("cat_single_action", "")
        cat_id = _safe_int(request.form.get("cat_id", "0"))
        try:
            target = None
            for cat in sf.cats.cats:
                if cat.id == cat_id:
                    target = cat
                    break
            if target is None:
                flash(f"Cat ID {cat_id} not found")
                return redirect(url_for("index"))

            if action == "own":
                target.unlock(sf)
                flash(f"Cat {cat_id} unlocked")
            elif action == "unown":
                target.remove(reset=True, save_file=sf)
                flash(f"Cat {cat_id} removed")
            elif action == "level":
                base = _safe_int(request.form.get("base", "0"))
                plus = _safe_int(request.form.get("plus", "0"))
                target.upgrade.base = base
                target.upgrade.plus = plus
                flash(f"Cat {cat_id} level set to {base+1}+{plus}")
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))

    @app.route("/edit/special_skills", methods=["POST"])
    def edit_special_skills():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        try:
            BasicItems.edit_special_skills(sf)
            _save_session_save(session_id, sf)
            flash("Special skills edited")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------
def _register_map_routes(app: Flask):
    @app.route("/edit/map", methods=["POST"])
    def edit_map():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("map_action", "")
        try:
            if action == "clear_tutorial":
                clear_tutorial(sf, True)
                flash("Tutorial cleared")
            elif action == "clear_story":
                web_edits.clear_story(sf)
                flash("Story chapters cleared")
            elif action == "max_treasures":
                web_edits.max_treasures(sf)
                flash("All treasures set to max")
            elif action == "max_outbreaks":
                web_edits.max_outbreaks(sf)
                flash("All outbreaks cleared")
            elif action == "max_aku":
                web_edits.clear_aku(sf)
                flash("Aku realms cleared")
            elif action == "max_uncanny":
                web_edits.clear_uncanny(sf)
                flash("Uncanny legends cleared")
            elif action == "max_zero_legends":
                web_edits.clear_zero_legends(sf)
                flash("Zero legends cleared")
            elif action == "max_towers":
                web_edits.clear_towers(sf)
                flash("Towers cleared")
            elif action == "max_legend_quest":
                web_edits.clear_legend_quest(sf)
                flash("Legend quest cleared")
            elif action == "max_gauntlets":
                web_edits.clear_gauntlets(sf)
                flash("Gauntlets cleared")
            elif action == "max_event":
                web_edits.clear_events(sf)
                flash("Event stages cleared")
            elif action == "max_sol":
                web_edits.clear_sol(sf)
                flash("Sol stages cleared")
            elif action == "max_collab":
                web_edits.clear_collab(sf)
                flash("Collab stages cleared")
            elif action == "unlock_aku_realm":
                unlock_aku_realm(sf)
                flash("Aku realm unlocked")
            elif action == "max_enigma":
                web_edits.clear_enigma_clears(sf)
                flash("Enigma stages cleared")
            elif action == "challenge_score":
                web_edits.max_challenge_score(sf)
                flash("Challenge score maxed")
            elif action == "dojo_score":
                web_edits.max_dojo_score(sf)
                flash("Dojo score maxed")
            elif action == "itf_timed_scores":
                StoryChapters.edit_itf_timed_scores(sf)
                flash("ITF timed scores set")
            elif action == "catamin_stages":
                web_edits.clear_catamin_stages(sf)
                flash("Catamin stages cleared")
            elif action == "behemoth_culling":
                web_edits.clear_behemoth_culling(sf)
                flash("Behemoth culling cleared")
            elif action == "enigma_stages":
                web_edits.clear_enigma_clears(sf)
                flash("Enigma stages cleared")
            elif action == "collab_gauntlets":
                web_edits.clear_collab_gauntlets(sf)
                flash("Collab gauntlets cleared")
            elif action == "filibuster":
                BasicItems.allow_filibuster_stage_reclearing(sf)
                flash("Filibuster reclearing enabled")
            elif action == "catclaw":
                web_edits.clear_catclaw(sf)
                flash("Catclaw championships cleared")
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Gamatoto
# ---------------------------------------------------------------------------
def _register_gamatoto_routes(app: Flask):
    @app.route("/edit/gamatoto", methods=["POST"])
    def edit_gamatoto():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("gamatoto_action", "")
        try:
            if action == "engineers":
                web_edits.max_engineers(sf)
                flash("Engineers maxed out")
            elif action == "base_materials":
                web_edits.max_base_materials(sf)
                flash("Base materials maxed out")
            elif action == "gamatoto_xp":
                web_edits.max_gamatoto_xp(sf)
                flash("Gamatoto XP maxed out")
            elif action == "gamatoto_helpers":
                web_edits.max_gamatoto_helpers(sf)
                flash("All gamatoto helpers added")
            elif action == "ototo_cannon":
                web_edits.max_ototo_cannon(sf)
                flash("Ototo cannon maxed")
            elif action == "cat_shrine":
                web_edits.max_cat_shrine(sf)
                flash("Cat shrine maxed")
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
def _register_account_routes(app: Flask):
    @app.route("/edit/account", methods=["POST"])
    def edit_account():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("account_action", "")
        try:
            if action == "inquiry_code":
                val = request.form.get("value", "")
                sf.inquiry_code = val
                flash("Inquiry code updated")
            elif action == "password_refresh_token":
                val = request.form.get("value", "")
                sf.password_refresh_token = val
                flash("Password refresh token updated")
            elif action == "upload_items":
                from bcsfe.cli.save_management import SaveManagement
                SaveManagement.upload_items(sf)
            elif action == "unban":
                ServerHandler(sf).create_new_account()
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
            flash(f"Account action '{action}' completed")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Fixes
# ---------------------------------------------------------------------------
def _register_fix_routes(app: Flask):
    @app.route("/edit/fix", methods=["POST"])
    def edit_fix():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("fix_action", "")
        try:
            if action == "fix_gamatoto":
                Fixes.fix_gamatoto_crash(sf)
            elif action == "fix_ototo":
                Fixes.fix_ototo_crash(sf)
            elif action == "fix_time":
                Fixes.fix_time_errors(sf)
            elif action == "fix_officer_pass":
                OfficerPass.fix_crash(sf)
            elif action == "unlock_equip":
                BasicItems.unlock_equip_menu(sf)
            else:
                flash(f"Unknown fix: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
            flash(f"Fix '{action}' applied")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Other
# ---------------------------------------------------------------------------
def _register_other_routes(app: Flask):
    @app.route("/edit/other", methods=["POST"])
    def edit_other():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        action = request.form.get("other_action", "")
        try:
            if action == "reset_gambling":
                GamblingEvent.reset_events(sf)
            elif action == "restart_pack":
                BasicItems.set_restart_pack(sf)
            elif action == "playtime":
                hours = _safe_int(request.form.get("hours", "0"))
                mins = _safe_int(request.form.get("minutes", "0"))
                secs = _safe_int(request.form.get("seconds", "0"))
                PlayTime.edit(sf, hours, mins, secs)
            elif action == "enemy_guide":
                web_edits.max_enemy_guide(sf)
                flash("Enemy guide maxed")
            elif action == "user_rank_rewards":
                web_edits.max_user_rank_rewards(sf)
                flash("User rank rewards claimed")
            elif action == "gold_pass":
                web_edits.max_gold_pass(sf)
                flash("Gold pass enabled")
            elif action == "medals":
                Medals.edit_medals(sf)
            elif action == "missions":
                Missions.edit_missions(sf)
            elif action == "talent_orbs":
                import json
                orb_data = request.form.get("orb_data", "[]")
                SaveOrbs.edit_talent_orbs(sf)
            elif action == "special_skills":
                BasicItems.edit_special_skills(sf)
            elif action == "scheme_items":
                web_edits.max_scheme_items(sf)
                flash("Scheme items maxed")
            else:
                flash(f"Unknown action: {action}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
            flash(f"Action '{action}' completed")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Seed editing
# ---------------------------------------------------------------------------
def _register_seed_routes(app: Flask):
    @app.route("/edit/seed", methods=["POST"])
    def edit_seed():
        session_id = session.get("save_id")
        sf = _get_session_save(session_id)
        if sf is None:
            flash("No save file loaded")
            return redirect(url_for("index"))
        field = request.form.get("seed_field", "")
        value = _safe_int(request.form.get("value", "0"))
        try:
            if field == "rare_gatya_seed":
                sf.gatya.rare_seed = value
            elif field == "normal_gatya_seed":
                sf.gatya.normal_seed = value
            elif field == "event_gatya_seed":
                sf.gatya.event_seed = value
            else:
                flash(f"Unknown seed field: {field}")
                return redirect(url_for("index"))
            _save_session_save(session_id, sf)
            flash("Seed updated")
        except Exception as e:
            flash(f"Error: {e}")
        return redirect(url_for("index"))




# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _register_config_routes(app: Flask):
    @app.route("/set_lang", methods=["POST"])
    def set_lang():
        lang = request.form.get("lang", "en")
        if lang in ("en", "zh-Hant"):
            session["ui_lang"] = lang
            flash(f"UI language set to {'中文' if lang == 'zh-Hant' else 'English'}")
        return redirect(url_for("index"))

    @app.route("/config", methods=["POST"])
    def edit_config():
        for key_enum in _CONFIG_DESCRIPTIONS:
            field_name = key_enum.value
            raw = request.form.get(field_name)
            if raw is None:
                continue
            _, kind = _CONFIG_DESCRIPTIONS[key_enum]
            try:
                if kind == "boolean":
                    val = raw == "true"
                elif kind == "int":
                    val = _safe_int(raw)
                else:
                    val = raw
                core.core_data.config.set(key_enum, val)
            except Exception:
                pass
        core.core_data.config.save()
        flash("Configuration saved")
        return redirect(url_for("index"))


if __name__ == "__main__":
    # Allow running as: PYTHONPATH=src python src/bcsfe/webui/app.py
    import sys
    import os as _os
    # Ensure the src directory is in the path when running directly
    _this_dir = _os.path.dirname(_os.path.abspath(__file__))
    _src_dir = _os.path.abspath(_os.path.join(_this_dir, "..", ".."))
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    from bcsfe.webui import run_webui
    run_webui()
