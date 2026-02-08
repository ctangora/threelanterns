ALLOWED_SOURCE_EXTENSIONS = {".txt", ".md", ".html", ".epub", ".gz", ".pdf", ".docx", ".rtf"}

REGION_VOCABULARY = {
    "africa_nile",
    "west_central_asia",
    "south_asia",
    "east_asia",
    "europe_mediterranean",
    "americas_indigenous",
}

TRADITION_VOCABULARY = {
    "celtic",
    "greek_mystery",
    "zoroastrian",
    "grimoire_tradition",
    "mesopotamian_ritual",
    "vedic_ritual",
    "daoist_ritual",
    "yoruba_orisha",
    "andean_ritual",
    "mesoamerican_ritual",
    "early_jewish_apocalyptic",
    "late_antique_esoteric",
}

ONTOLOGY_DIMENSIONS = {
    "ritual_intent": {
        "healing",
        "protection",
        "purification",
        "fertility_abundance",
        "initiation_transition",
        "divination",
        "spirit_contact",
        "curse_binding",
        "atonement_repair",
        "sovereignty_legitimation",
    },
    "ritual_actors": {
        "specialist_priest",
        "household_practitioner",
        "initiate_group",
        "ruler_state_actor",
        "community_collective",
        "spirit_nonhuman_agent",
    },
    "ritual_actions": {
        "invocation",
        "chant_recitation",
        "anointing",
        "offering_deposit",
        "fire_operation",
        "water_operation",
        "gesture_sequence",
        "circumambulation",
        "inscription_writing",
        "burial_interment",
    },
    "materials_tools": {
        "plant_materia",
        "mineral_materia",
        "animal_materia",
        "vessel_container",
        "blade_tool",
        "cord_binding_material",
        "lamp_flame",
        "tablet_scroll",
        "powder_incense",
        "liquid_elixir",
    },
    "time_timing": {
        "seasonal_calendar",
        "lunar_phase",
        "solar_marker",
        "night_operation",
        "dawn_operation",
        "hourly_auspicious_window",
        "life_cycle_event",
    },
    "location_setting": {
        "domestic_space",
        "temple_sanctuary",
        "open_landscape",
        "water_edge",
        "burial_site",
        "threshold_crossing",
        "restricted_chamber",
    },
    "invocation_structure": {
        "deity_address",
        "ancestor_address",
        "angelic_hierarchy",
        "spirit_command",
        "formulaic_epithet_sequence",
        "vow_oath_clause",
    },
    "exchange_offering": {
        "food_offering",
        "liquid_libation",
        "burnt_offering",
        "votive_object",
        "spoken_vow_exchange",
        "service_obligation",
    },
    "protection_boundary": {
        "circle_boundary",
        "threshold_marking",
        "name_seal",
        "apotropaic_symbol",
        "protective_text_inscription",
        "guardianship_invocation",
    },
    "divination_modality": {
        "lot_casting",
        "dream_incubation",
        "omen_reading",
        "astrological_reading",
        "scrying_surface",
        "mediumship",
    },
    "outcome_claim": {
        "material_change",
        "status_change",
        "knowledge_revelation",
        "protection_confirmed",
        "curse_effect_claim",
        "healing_claim",
        "uncertain_or_symbolic",
    },
}

FLAG_TYPES = {
    "uncertain_translation",
    "hostile_source_frame",
    "provenance_gap",
    "date_uncertainty",
    "conflicting_witnesses",
}

COMMONALITY_RELATION_TYPES = {"isVersionOf", "isRelatedTo", "sharesPatternWith", "isDerivativeOf"}

LANGUAGE_NORMALIZED_CANONICAL = "eng"
