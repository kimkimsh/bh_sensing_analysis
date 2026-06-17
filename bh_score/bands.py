"""LED <-> wavelength band map and per-menu rule skeleton (Phase-0 FROZEN).

The LED table below is the canonical 16-row map verified from the live engine
(PropertiesDatabase.h:113-128; see SCORING_SPEC §6). It is pure data and is safe
to freeze in pre-setup.

The doneness cascade thresholds themselves are NOT transcribed here: PLAN §6
requires them to be ported directly from the live C++ headers (not from the spec
prose) for fidelity, which is the build's blocking Phase-0 task. This module only
exposes the band map + the menu offset-channel policy + an empty menu-rule slot.
"""

# (min, max, peak) per ledId — the band key is the full triple, because 720nm is
# ambiguous: led9 = (720,750,730) vs led10 = (720,740,740). led15 = sentinel.
LED_BANDS = {
    0:  (410, 420, 415),
    1:  (440, 460, 450),
    2:  (460, 480, 470),   # meatSegNet ch0
    3:  (515, 540, 527),
    4:  (520, 610, 567),   # meatSegNet ch1 (peak 567 — NOT led3)
    5:  (585, 595, 590),
    6:  (610, 620, 615),
    7:  (620, 630, 625),
    8:  (650, 670, 660),   # meatSegNet ch2
    9:  (720, 750, 730),   # ambiguous 720nm — distinguished by peak 730
    10: (720, 740, 740),   # meatSegNet ch3 — ambiguous 720nm — peak 740; doneness rules use this
    11: (800, 830, 810),
    12: (840, 870, 850),   # meatSegNet ch4
    13: (870, 910, 890),
    14: (930, 970, 940),
    15: (999, 999, 999),   # sentinel — dropped during cube grouping
}

# meatSegNet 5-channel input order (led ids -> channels ch0..ch4).
MEATSEGNET_INPUT_LEDS = (2, 4, 8, 10, 12)

# Band-key triple of the sentinel that must be dropped while grouping a capture.
SENTINEL_BAND = (999, 999, 999)

# (min, max, peak) -> ledId reverse lookup (peak disambiguates the 720nm collision).
BAND_TO_LED = {triple: led for led, triple in LED_BANDS.items()}


def ledByBand(wMin, wMax, wPeak):
    """Return the ledId for a (min, max, peak) band key, or None if unmapped."""
    return BAND_TO_LED.get((wMin, wMax, wPeak))


def bandByLed(ledId):
    """Return the (min, max, peak) triple for a ledId, or None."""
    return LED_BANDS.get(ledId)


# Per-menu offset-channel policy (SCORING_SPEC §4, verified). beef applies the
# offset to all three classes; pork only to burnt. The kernel reads this rather
# than applying a uniform 3-channel offset.
OFFSET_CHANNELS = {
    "beef/striploin": ("burnt", "slightly_burnt", "proper"),
    "pork/belly": ("burnt",),
}

# Per-menu doneness rule table. SKELETON ONLY — the build's Phase-0 step ports the
# exact gate/burnt/slightly/proper thresholds from the live C++ headers
# (ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158, etc.). Do not fill
# these from SCORING_SPEC prose; port from the live .h for fidelity.
MENU_RULES = {
    # "beef/striploin": <ported from live header in Phase 0>,
}
