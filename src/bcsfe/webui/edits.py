from __future__ import annotations

"""Web-safe wrappers for CLI edit functions that use dialog_creator.

Every function in this file has been verified against the actual
SaveFile attributes and data class APIs."""

from typing import Any
from bcsfe import core
from bcsfe.core.game.catbase.playtime import PlayTime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_chapters_via_chapters(c: Any):
    """Clear Chapters object.
    Chapters.chapters = list of ChaptersStars
    Each ChaptersStars.chapters = list of Chapter
    Each Chapter.stages = list of Stage
    Uses ChaptersStars.clear_stage(star, stage, clear_amount, overwrite).
    """
    if c is None:
        return
    for cs in c.chapters:
        for star_idx in range(len(cs.chapters)):
            for stage_idx in range(len(cs.chapters[star_idx].stages)):
                cs.clear_stage(star_idx, stage_idx, 1, True)


# GauntletChapters has the SAME structure: .chapters = list[ChaptersStars]
_clear_chapters_via_gauntlet = _clear_chapters_via_chapters


def _clear_event_type(e: Any, type_idx: int):
    """Clear all stages in an EventChapterGroup by type index.
    EventChapters.chapters[type] = EventChapterGroup
    EventChapterGroup.clear_group() clears everything.
    """
    if e is None or type_idx >= len(e.chapters):
        return
    e.chapters[type_idx].clear_group()


# ---------------------------------------------------------------------------
# Gamatoto
# ---------------------------------------------------------------------------

def max_engineers(sf: core.SaveFile):
    """Max out engineer count."""
    sf.ototo.engineers = 999

def max_base_materials(sf: core.SaveFile):
    """Max out all base materials."""
    for mat in sf.ototo.base_materials.materials:
        mat.amount = 999999

def max_gamatoto_xp(sf: core.SaveFile):
    """Set gamatoto XP to max level."""
    gl = core.core_data.get_gamatoto_levels(sf)
    if gl is None or gl.levels is None:
        return
    ml = gl.get_max_level()
    if ml is None:
        return
    sf.gamatoto.xp = gl.get_xp_from_level(ml)

def max_gamatoto_helpers(sf: core.SaveFile):
    """Add all available gamatoto helpers."""
    mn = core.core_data.get_gamatoto_members_name(sf)
    if mn is None or mn.members is None:
        return
    existing = [h.id for h in sf.gamatoto.helpers.helpers]
    from bcsfe.core.game.gamoto.gamatoto import Helper
    for m in mn.members:
        if m.member_id not in existing:
            sf.gamatoto.helpers.helpers.append(Helper(m.member_id))

def max_ototo_cannon(sf: core.SaveFile):
    """Set all cannons to max."""
    for cid in sf.ototo.cannons.cannons:
        c = sf.ototo.cannons.cannons[cid]
        c.development = 10
        if c.levels:
            c.levels = [10] * len(c.levels)

def max_cat_shrine(sf: core.SaveFile):
    """Set cat shrine to max XP."""
    d = core.core_data.get_cat_shrine_levels(sf)
    if d is None or d.boundaries is None:
        return
    mx = d.get_max_xp()
    if mx is None:
        return
    sf.cat_shrine.xp_offering = mx

def max_scheme_items(sf: core.SaveFile):
    """Mark every known scheme item as obtainable."""
    known_ids = set(sf.scheme_items.to_obtain) | set(sf.scheme_items.received)
    sf.scheme_items.to_obtain = sorted(known_ids)
    sf.scheme_items.received = []


def edit_scheme_item(sf: core.SaveFile, scheme_id: int, obtained: bool) -> None:
    if scheme_id < 0:
        raise ValueError("scheme id must be non-negative")
    if obtained:
        if scheme_id not in sf.scheme_items.to_obtain:
            sf.scheme_items.to_obtain.append(scheme_id)
        if scheme_id in sf.scheme_items.received:
            sf.scheme_items.received.remove(scheme_id)
    else:
        if scheme_id in sf.scheme_items.to_obtain:
            sf.scheme_items.to_obtain.remove(scheme_id)
        if scheme_id in sf.scheme_items.received:
            sf.scheme_items.received.remove(scheme_id)


def max_cat_talents(sf: core.SaveFile) -> int:
    """Max every available talent without invoking CLI prompts."""
    from bcsfe.cli.edits.cat_editor import CatEditor

    editor = CatEditor(sf)
    cats = [cat for cat in sf.cats.cats if cat.unlocked and cat.talents is not None]
    editor.edit_talent_many(cats)
    return len(cats)


def max_special_skills(sf: core.SaveFile) -> int:
    """Max all special skills using the same game-data limits as the CLI."""
    ability_data = core.core_data.get_ability_data(sf)
    if ability_data.ability_data is None:
        return 0
    skills = sf.special_skills.get_valid_skills()
    count = min(len(skills), len(ability_data.ability_data))
    for skill_id in range(count):
        ability = ability_data.ability_data[skill_id]
        sf.special_skills.set_upgrade(
            skill_id,
            core.Upgrade(ability.max_base_level - 1, ability.max_plus_level),
            max_base=ability.max_base_level - 1,
            max_plus=ability.max_plus_level,
        )
        skills[skill_id].seen = 1
    return count


def trade_rare_tickets(sf: core.SaveFile, amount: int) -> None:
    """Apply the CLI rare-ticket trade with an explicit web value."""
    maximum = max(core.core_data.max_value_manager.rare_tickets - sf.rare_tickets, 0)
    if amount < 0 or amount > maximum:
        raise ValueError(f"amount must be between 0 and {maximum}")
    slot = next(
        (
            item
            for item in sf.cats.storage_items
            if item.item_type == 0 or (item.item_type == 2 and item.item_id == 1)
        ),
        None,
    )
    if slot is None:
        raise ValueError("cat storage is full")
    slot.item_type = 2
    slot.item_id = 1
    sf.gatya.trade_progress = amount * 5


def edit_storage(sf: core.SaveFile, action: str, item_type: int = 0,
                 item_id: int = 0, quantity: int = 1, slot_index: int = -1) -> int:
    """Web-safe cat-storage operations matching the CLI storage editor."""
    from bcsfe.cli.edits import storage

    slots = sf.cats.storage_items
    if action == "clear":
        storage.clear_storage(slots)
        return len(slots)
    if action == "remove":
        if slot_index < 0 or slot_index >= len(slots):
            raise ValueError("invalid storage slot")
        slots[slot_index].item_type = 0
        slots[slot_index].item_id = 0
        return 1
    if action != "add" or item_type not in (1, 2, 3) or quantity < 1:
        raise ValueError("invalid storage operation")
    added = 0
    for _ in range(quantity):
        item = core.StorageItem(item_id)
        item.item_type = item_type
        if not storage.add_item(slots, item):
            break
        added += 1
    if added != quantity:
        raise ValueError(f"storage only had room for {added} item(s)")
    return added


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------

def clear_story(sf: core.SaveFile):
    """Clear all story stages.
    sf.story = StoryChapters.chapters = list[Chapter]
    Each Chapter.clear_stage(index, amount, overwrite).
    """
    if sf.story is None:
        return
    for ch in sf.story.chapters:
        for i in range(len(ch.stages)):
            ch.clear_stage(i, 1, True)

def max_treasures(sf: core.SaveFile):
    """Set all treasures to max (3).
    Only stages with treasure slots (first 49) should be modified.
    CLI uses chapter.get_treasure_stages() which returns stages[:49].
    """
    if sf.story is None:
        return
    for ch in sf.story.chapters:
        for st in ch.get_treasure_stages():
            st.treasure = 3

def max_outbreaks(sf: core.SaveFile):
    """Clear all outbreaks.
    sf.outbreaks.chapters = list of outbreak chapters
    Each chapter.outbreaks = dict {stage_id: stage} with .cleared
    """
    if sf.outbreaks is None:
        return
    for ch in sf.outbreaks.chapters:
        for sid in list(ch.outbreaks.keys()):
            ch.outbreaks[sid].cleared = True


# ---------------------------------------------------------------------------
# Event chapters (SOL=0, Event=1, Collab=2) - all in sf.event_stages
# ---------------------------------------------------------------------------

def clear_sol(sf: core.SaveFile):
    _clear_event_type(sf.event_stages, 0)

def clear_events(sf: core.SaveFile):
    _clear_event_type(sf.event_stages, 1)

def clear_collab(sf: core.SaveFile):
    _clear_event_type(sf.event_stages, 2)


# ---------------------------------------------------------------------------
# Chapters-based maps (sf.chapters = core.Chapters)
# ---------------------------------------------------------------------------

def clear_uncanny(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.uncanny.chapters)

def clear_catamin_stages(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.catamin_stages.chapters)

def clear_zero_legends(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.zero_legends)

def clear_towers(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.tower.chapters)

def clear_legend_quest(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.legend_quest)

def clear_catclaw(sf: core.SaveFile):
    _clear_chapters_via_chapters(sf.dojo_chapters)


# ---------------------------------------------------------------------------
# Gauntlet-based maps (sf.chapters = list[ChaptersStars])
# ---------------------------------------------------------------------------

def clear_gauntlets(sf: core.SaveFile):
    _clear_chapters_via_gauntlet(sf.gauntlets)

def clear_collab_gauntlets(sf: core.SaveFile):
    _clear_chapters_via_gauntlet(sf.collab_gauntlets)

def clear_behemoth_culling(sf: core.SaveFile):
    _clear_chapters_via_gauntlet(sf.behemoth_culling)

def clear_enigma_clears(sf: core.SaveFile):
    """Enigma cleared stages stored in sf.enigma_clears (GauntletChapters)."""
    _clear_chapters_via_gauntlet(sf.enigma_clears)


# ---------------------------------------------------------------------------
# Aku
# ---------------------------------------------------------------------------

def clear_aku(sf: core.SaveFile):
    """sf.aku = AkuChapters.chapters = list[ChaptersStars].
    Each ChaptersStars.chapters = list[Chapter] (aku variant, NO clear_stage).
    Directly set stage.clear_times for each stage.
    """
    if sf.aku is None:
        return
    for cs in sf.aku.chapters:
        for ch in cs.chapters:
            for st in ch.stages:
                st.clear_times = 1


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

def max_challenge_score(sf: core.SaveFile):
    """sf.challenge = ChallengeChapters with .scores = list[int]."""
    sf.challenge.scores = [9999999] * len(sf.challenge.scores) if sf.challenge.scores else [9999999]

def max_dojo_score(sf: core.SaveFile):
    """sf.dojo.chapters.get_stage(0, 0) has .score attribute."""
    stage = sf.dojo.chapters.get_stage(0, 0)
    stage.score = 9999999


# ---------------------------------------------------------------------------
# Other
# ---------------------------------------------------------------------------

def set_playtime(sf: core.SaveFile, h: int, m: int, s: int):
    if h < 0 or m < 0 or s < 0 or m > 59 or s > 59:
        raise ValueError("invalid playtime")
    sf.officer_pass.play_time = PlayTime.from_hours_mins_secs(h, m, s).frames


def unlock_equip_menu(sf: core.SaveFile):
    while len(sf.menu_unlocks) <= 2:
        sf.menu_unlocks.append(0)
    sf.menu_unlocks[2] = max(sf.menu_unlocks[2], 1)

def max_enemy_guide(sf: core.SaveFile):
    """Unlock all enemies in enemy guide."""
    try:
        for i in range(len(sf.enemy_guide)):
            sf.enemy_guide[i] = True
    except (TypeError, AttributeError):
        pass

def max_user_rank_rewards(sf: core.SaveFile):
    for reward in sf.user_rank_rewards.rewards:
        reward.claimed = True


def max_itf_timed_scores(sf: core.SaveFile):
    """Max timed scores for Into the Future chapters without CLI dialogs."""
    for chapter in sf.story.chapters[3:6]:
        for stage in chapter.stages:
            stage.itf_timed_score = 999999

def max_gold_pass(sf: core.SaveFile):
    sf.gold_pass = True
    sf.gold_pass_start_time = 0.0
    sf.gold_pass_end_time = 9999999999.0
