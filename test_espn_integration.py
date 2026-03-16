#!/usr/bin/env python3
"""Test ESPN picks integration with existing data files."""

import sys
from src.scout import parse_espn_api_response, build_espn_name_mapping
from src.utils import load_json

def test_name_mapping():
    """Test that name mapping works correctly."""
    print("Testing name mapping...")
    name_map = build_espn_name_mapping('data/real_bracket_2026.json')
    
    # Test some known mappings
    assert name_map['ILL'] == 'Illinois', f"Expected Illinois, got {name_map.get('ILL')}"
    assert name_map['DUKE'] == 'Duke', f"Expected Duke, got {name_map.get('DUKE')}"
    assert name_map['CONN'] == 'UConn', f"Expected UConn, got {name_map.get('CONN')}"
    assert name_map['TA&M'] == 'Texas A&M', f"Expected Texas A&M, got {name_map.get('TA&M')}"
    
    print(f"✓ Name mapping works ({len(name_map)} mappings)")
    return name_map

def test_parser():
    """Test ESPN API response parser."""
    print("\nTesting ESPN API response parser...")
    
    # Load existing ESPN data files
    challenge_data = load_json('data/espn_challenge_2026.json')
    props_data = load_json('data/espn_propositions_2026.json')
    
    # Build mock API response
    api_response = {
        'propositions': challenge_data['propositions'] + props_data
    }
    
    # Parse
    picks = parse_espn_api_response(api_response, 2026, 'data')
    
    print(f"✓ Parsed {len(picks)} teams")
    
    # Verify key teams have data
    assert 'Duke' in picks, "Duke not found in picks"
    assert 'Illinois' in picks, "Illinois not found in picks"
    assert 'Arizona' in picks, "Arizona not found in picks"
    
    # Verify rounds are present
    duke_picks = picks['Duke']
    assert 1 in duke_picks, "R1 missing for Duke"
    assert 6 in duke_picks, "Title missing for Duke"
    
    # Verify reasonable values
    assert 0.9 < duke_picks[1] < 1.0, f"Duke R1 pick % unreasonable: {duke_picks[1]}"
    assert 0.1 < duke_picks[6] < 0.5, f"Duke title pick % unreasonable: {duke_picks[6]}"
    
    # Verify interpolation
    assert 2 in duke_picks, "R2 missing (interpolation failed)"
    assert 3 in duke_picks, "R3 missing (interpolation failed)"
    
    print(f"✓ Duke: R1={duke_picks[1]:.3f}, R2={duke_picks[2]:.3f}, Title={duke_picks[6]:.4f}")
    print(f"✓ All validations passed")
    
    return picks

def test_integration():
    """Test full integration with contrarian.py."""
    print("\nTesting integration with ownership analysis...")
    
    from src.models import Team
    from src.contrarian import build_ownership_profiles
    
    # Load teams
    teams_data = load_json('data/teams.json')
    teams = [Team.from_dict(t) for t in teams_data]
    
    # Load picks
    challenge_data = load_json('data/espn_challenge_2026.json')
    props_data = load_json('data/espn_propositions_2026.json')
    api_response = {'propositions': challenge_data['propositions'] + props_data}
    espn_picks = parse_espn_api_response(api_response, 2026, 'data')
    
    # Build ownership profiles
    profiles = build_ownership_profiles(teams, espn_picks)
    
    print(f"✓ Built {len(profiles)} ownership profiles")
    
    # Find Duke's profile
    duke_profile = next((p for p in profiles if p.team == 'Duke'), None)
    assert duke_profile is not None, "Duke profile not found"
    
    # Verify ownership data is present
    assert 1 in duke_profile.round_ownership, "R1 ownership missing"
    assert duke_profile.title_ownership > 0, "Title ownership missing"
    
    print(f"✓ Duke ownership: R1={duke_profile.round_ownership[1]:.3f}, Title={duke_profile.title_ownership:.4f}")
    
    return profiles

def main():
    """Run all tests."""
    print("=" * 60)
    print("ESPN Picks Integration Test Suite")
    print("=" * 60)
    
    try:
        name_map = test_name_mapping()
        picks = test_parser()
        profiles = test_integration()
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"  - Name mappings: {len(name_map)}")
        print(f"  - Teams with pick data: {len(picks)}")
        print(f"  - Ownership profiles: {len(profiles)}")
        
        return 0
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 2

if __name__ == '__main__':
    sys.exit(main())
