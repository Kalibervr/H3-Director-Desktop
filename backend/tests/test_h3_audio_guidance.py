from services.h3_audio_guidance import H3AudioGuidance, audio_summary, compose_h3_prompt


def test_natural_ambience_with_controls_is_deterministic() -> None:
    guidance = H3AudioGuidance(no_speech=True, no_music=True, custom_instruction="footsteps in snow")
    result = compose_h3_prompt("A lantern in a snowy forest.", guidance)
    assert result == "A lantern in a snowy forest. Natural environmental ambience appropriate to the scene. footsteps in snow No speech, no dialogue, no voices, no vocalizations. No music, no soundtrack, no background score, no singing, no musical elements."


def test_dialogue_preserves_original_without_inventing_text() -> None:
    result = compose_h3_prompt("A woman says hello.", H3AudioGuidance(mode="dialogue", no_music=True))
    assert result == "A woman says hello. No music, no soundtrack, no background score, no singing, no musical elements."


def test_audio_guidance_is_idempotent_when_developed_prompt_already_contains_it() -> None:
    result = compose_h3_prompt(
        "A quiet elevator interior. Natural environmental ambience appropriate to the scene.",
        H3AudioGuidance(mode="natural_ambience", no_speech=True, no_music=True),
    )
    assert result.count("Natural environmental ambience appropriate to the scene.") == 1
    assert result.count("No speech, no dialogue, no voices, no vocalizations.") == 1
    assert result.count("No music, no soundtrack, no background score, no singing, no musical elements.") == 1


def test_silent_has_precedence_over_conflicting_audio_options() -> None:
    guidance = H3AudioGuidance(mode="silent", no_speech=False, no_music=False, custom_instruction="birds singing")
    result = compose_h3_prompt("A quiet room.", guidance)
    assert result == "A quiet room. No speech, no dialogue, no voices, no vocalizations, no music, no soundtrack, no background score, no singing, no musical elements, no ambient sound."
    assert audio_summary(guidance) == "Silent"
