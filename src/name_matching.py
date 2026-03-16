"""Shared team name normalization for matching across data sources.

Extracted from upset_model/train_sklearn.py to be shared between training
and the live prediction pipeline (src/enrich.py, src/load_real_bracket.py).
"""

import re
from typing import Optional


def normalize_team_name(name: str) -> str:
    """Normalize team names for joining (handle common aliases).

    This is the canonical normalization used across all data sources.
    """
    name = name.strip()

    aliases = {
        'Ohio St. 1': 'Ohio St.',
        'Ohio State': 'Ohio St.',
        'UConn': 'Connecticut',
        "St. John's": "St. John's (NY)",
        'Miami': 'Miami FL',
        'Southern California': 'USC',
        'LSU': 'Louisiana St.',
        'VCU': 'Virginia Commonwealth',
        'UNLV': 'Nevada Las Vegas',
        'UNC': 'North Carolina',
        'UCSB': 'UC Santa Barbara',
        'UCF': 'Central Florida',
        'SMU': 'Southern Methodist',
        'BYU': 'Brigham Young',
        'TCU': 'Texas Christian',
        'LIU': 'Long Island',
        'UMBC': 'Maryland Baltimore County',
        'UNC Asheville': 'UNC Asheville',
        "St. Mary's": "Saint Mary's",
        'St. Bonaventure': 'St. Bonaventure',
        'Mississippi': 'Ole Miss',
        'College of Charleston': 'Col. of Charleston',
        'Miami (FL)': 'Miami FL',
        "St. Mary's (CA)": "Saint Mary's",
        "Saint Mary's (CA)": "Saint Mary's",
        'NC State': 'N.C. State',
        'North Carolina St.': 'N.C. State',
        'FGCU': 'Florida Gulf Coast',
        'FDU': 'Fairleigh Dickinson',
        'SFA': 'Stephen F. Austin',
        'UNI': 'Northern Iowa',
        'Middle Tenn.': 'Middle Tennessee',
        'Northern Ky.': 'Northern Kentucky',
        'Eastern Wash.': 'Eastern Washington',
        'Coastal Caro.': 'Coastal Carolina',
        'Western Ky.': 'Western Kentucky',
        'Northern Colo.': 'Northern Colorado',
        'Boston U.': 'Boston University',
        'App State': 'Appalachian St.',
        "Mt. St. Mary's": "Mount St. Mary's",
        'Albany (NY)': 'Albany',
        'Fla. Atlantic': 'Florida Atlantic',
        'Col. of Charleston': 'Charleston',
        'Gardner-Webb': 'Gardner Webb',
        'Loyola (IL)': 'Loyola Chicago',
        'UALR': 'Arkansas Little Rock',
        'Bakersfield': 'Cal St. Bakersfield',
        "Saint Peter's": "St. Peter's",
        'UTSA': 'Texas San Antonio',
        'Grambling': 'Grambling St.',
        'McNeese': 'McNeese St.',
        'Omaha': 'Nebraska Omaha',
        'UNCW': 'UNC Wilmington',
        'Southern U.': 'Southern',
        'N.C. Central': 'North Carolina Central',
        'N.C. A&T': 'North Carolina A&T',
        'East Tenn. St.': 'East Tennessee St.',
        'Eastern Ky.': 'Eastern Kentucky',
        'Western Mich.': 'Western Michigan',
        'Prairie View': 'Prairie View A&M',
        'A&M-Corpus Christi': 'Texas A&M Corpus Chris',
        'Southeast Mo. St.': 'Southeast Missouri St.',
        'Saint Louis': 'St. Louis',
        'NC Asheville': 'UNC Asheville',
        'Little Rock': 'Arkansas Little Rock',
        'Louisiana': 'Louisiana Lafayette',
    }

    for alias, canonical in aliases.items():
        if name == alias:
            return canonical

    name = re.sub(r'\s+\d+$', '', name)
    return name


def normalize_torvik_name(name: str) -> str:
    """Normalize Torvik team names to match KenPom/NCAA conventions."""
    torvik_aliases = {
        "St. John's": "St. John's (NY)",
        'Miami': 'Miami FL',
        'Miami (FL)': 'Miami FL',
        'UConn': 'Connecticut',
        'LSU': 'Louisiana St.',
        'VCU': 'Virginia Commonwealth',
        'UNLV': 'Nevada Las Vegas',
        'UNC': 'North Carolina',
        'UCSB': 'UC Santa Barbara',
        'UCF': 'Central Florida',
        'SMU': 'Southern Methodist',
        'BYU': 'Brigham Young',
        'TCU': 'Texas Christian',
        'UMBC': 'Maryland Baltimore County',
        'Mississippi': 'Ole Miss',
        'SIU Edwardsville': 'SIUE',
    }
    if name in torvik_aliases:
        return normalize_team_name(torvik_aliases[name])
    return normalize_team_name(name)


def normalize_lrmc_name(name: str) -> str:
    """Normalize LRMC team names to match KenPom/NCAA conventions.

    LRMC uses underscores, abbreviations, and inconsistent suffixes.
    """
    lrmc_aliases = {
        'SF_Austin': 'Stephen F. Austin',
        'FL_Atlantic': 'Florida Atlantic',
        'FL_Gulf_Coast': 'Florida Gulf Coast',
        'F_Dickinson': 'Fairleigh Dickinson',
        'G_Washington': 'George Washington',
        'VA_Commonwealth': 'Virginia Commonwealth',
        'Col_Charleston': 'Col. of Charleston',
        'Charleston_So': 'Charleston Southern',
        'American_Univ': 'American',
        'Loy_Marymount': 'Loyola Marymount',
        'Loyola_MD': 'Loyola Maryland',
        'IL_Chicago': 'Illinois Chicago',
        'TX_Southern': 'Texas Southern',
        'TX_A&M_Commerce': 'Texas A&M Commerce',
        'TAM_C._Christi': 'Texas A&M Corpus Chris',
        'TX_Pan_American': 'Texas Pan American',
        'Houston_Bap': 'Houston Baptist',
        'Houston_Chr': 'Houston Christian',
        'Cent_Arkansas': 'Central Arkansas',
        'Cent. Michigan': 'Central Michigan',
        'NC_A&T': 'North Carolina A&T',
        'NC_Central': 'North Carolina Central',
        'NC_State': 'N.C. State',
        'NE_Omaha': 'Nebraska Omaha',
        'Albany_NY': 'Albany',
        'Monmouth_NJ': 'Monmouth',
        'St_Francis_NY': 'St. Francis NY',
        'St_Francis_PA': 'St. Francis PA',
        "St_Joseph's_PA": "Saint Joseph's",
        "St_Mary's_CA": "Saint Mary's",
        "St_John's": "St. John's (NY)",
        "Mt_St_Mary's": "Mount St. Mary's",
        "St_Peter's": "St. Peter's",
        'St_Bonaventure': 'St. Bonaventure',
        'St_Louis': 'St. Louis',
        'St_Thomas_MN': 'St. Thomas',
        'MS_Valley_St': 'Mississippi Valley St.',
        'MD_E_Shore': 'Maryland Eastern Shore',
        'LIU_Brooklyn': 'Long Island',
        'TN_Martin': 'Tennessee Martin',
        'SUNY_Albany': 'Albany',
        'Missouri_KC': 'UMKC',
        'Prairie_View': 'Prairie View A&M',
        'Southern_Univ': 'Southern',
        'Northwestern_LA': 'Northwestern St.',
        'Queens_NC': 'Queens',
        'SC_Upstate': 'USC Upstate',
        'Incarnate_Word': 'Incarnate Word',
        'Dixie_St': 'Utah Tech',
        'Cal_Poly_SLO': 'Cal Poly',
        'MA_Lowell': 'UMass Lowell',
        'WI_Green_Bay': 'Green Bay',
        'WI_Milwaukee': 'Milwaukee',
        'Coastal_Car': 'Coastal Carolina',
        'S_Dakota_St': 'South Dakota St.',
        'N_Dakota_St': 'North Dakota St.',
        'Middle_Tenn_St': 'Middle Tennessee',
        'Middle Tenn. St.': 'Middle Tennessee',
        'Abilene_Chr': 'Abilene Christian',
        'W_Kentucky': 'Western Kentucky',
        'Ark_Little_Rock': 'Arkansas Little Rock',
        'UNC_Asheville': 'UNC Asheville',
        'Loyola-Chicago': 'Loyola Chicago',
        'N.C. Asheville': 'UNC Asheville',
        'Fla Gulf Coast': 'Florida Gulf Coast',
        'North. Kentucky': 'Northern Kentucky',
        'West. Kentucky': 'Western Kentucky',
        'E_Tennessee_St': 'East Tennessee St.',
    }

    if name in lrmc_aliases:
        return normalize_team_name(lrmc_aliases[name])

    name = name.replace('_', ' ')

    prefix_map = {
        'E ': 'Eastern ',
        'W ': 'Western ',
        'N ': 'Northern ',
        'S ': 'Southern ',
        'C ': 'Central ',
        'SE ': 'Southeast ',
    }
    for prefix, expansion in prefix_map.items():
        if name.startswith(prefix):
            name = expansion + name[len(prefix):]
            break

    if name.startswith('CS '):
        name = 'Cal St. ' + name[3:]

    name = re.sub(r'\bSt$', 'St.', name)

    return normalize_team_name(name)


def match_team_name(external_name: str, team_names: list[str],
                    source: str = "generic") -> Optional[str]:
    """Match an external team name to a team in the bracket.

    Args:
        external_name: Name from external source (Torvik, LRMC, etc.)
        team_names: List of team names from the bracket/KenPom
        source: "torvik", "lrmc", or "generic" — selects normalization

    Returns:
        Matched team name from team_names, or None if no match
    """
    # Normalize external name based on source
    if source == "torvik":
        norm_ext = normalize_torvik_name(external_name)
    elif source == "lrmc":
        norm_ext = normalize_lrmc_name(external_name)
    else:
        norm_ext = normalize_team_name(external_name)

    # Build normalized lookup
    norm_to_original = {}
    for name in team_names:
        norm_to_original[normalize_team_name(name)] = name

    # Exact match
    if norm_ext in norm_to_original:
        return norm_to_original[norm_ext]

    # Lowercase exact match (handle case differences)
    norm_ext_lower = norm_ext.lower()
    for norm, orig in norm_to_original.items():
        if norm.lower() == norm_ext_lower:
            return orig

    # Substring match (avoid short name false positives)
    short_names = {'iowa', 'miami', 'texas', 'carolina', 'virginia', 'tennessee',
                   'indiana', 'ohio', 'utah', 'oregon', 'michigan', 'georgia',
                   'kentucky', 'florida', 'alabama', 'colorado', 'arkansas',
                   'illinois', 'missouri', 'washington'}
    is_short = norm_ext_lower in short_names

    if not is_short:
        for norm, orig in norm_to_original.items():
            norm_lower = norm.lower()
            if (norm_ext_lower in norm_lower or norm_lower in norm_ext_lower) and len(norm_ext_lower) > 4:
                return orig

    return None
