import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import pytz

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="H2 Sports Master Dinger Engine")

# --- UI LAYER & REFRESH ---
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.title("⚾ H2 Sports Master Dinger Engine")
eastern = pytz.timezone("US/Eastern")
today = datetime.now(eastern).strftime('%Y-%m-%d')
st.subheader(f"Data for: {today}")


# --- DATA FETCHERS ---
@st.cache_data(ttl=3600)
def fetch_mlb_data(url, params=None):
    try:
        response = requests.get(url, params=params or {}, timeout=10)
        return response.json() if response.status_code == 200 else {}
    except:
        return {}


def get_pitcher_metrics(pitcher_id):
    if not pitcher_id:
        return {"Name": "TBD", "HR/9": 0.0, "K/9": 0.0, "ERA": 0.0, "WHIP": 0.0, "OBA": 0.0, "Hand": "R"}
    data = fetch_mlb_data(
        f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}?hydrate=stats(group=[pitching],type=[season])")
    try:
        p_data = data['people'][0]
        s = p_data['stats'][0]['splits'][0]['stat']
        so, ip = float(s.get('strikeOuts', 0)), float(s.get('inningsPitched', 0))
        return {
            "Name": p_data.get('fullName', 'TBD'),
            "Hand": p_data.get('pitchHand', {}).get('code', 'R'),
            "HR/9": float(s.get('homeRunsPer9', 0.0)),
            "K/9": (so / ip * 9) if ip > 0 else 0.0,
            "ERA": float(s.get('era', 0.0)),
            "WHIP": float(s.get('whip', 0.0)),
            "OBA": float(s.get('avg', 0.0))
        }
    except:
        return {"Name": "TBD", "Hand": "R", "HR/9": 0.0, "K/9": 0.0, "ERA": 0.0, "WHIP": 0.0, "OBA": 0.0}


def get_hitter_stats(player_id, p_met, b_hand, team_name):
    data = fetch_mlb_data(
        f"https://statsapi.mlb.com/api/v1/people/{player_id}?hydrate=stats(group=[hitting],type=[season])")
    try:
        p_data = data['people'][0]
        s = p_data['stats'][0]['splits'][0]['stat']
        hr, slg, avg, ops = float(s.get('homeRuns', 0)), float(s.get('slg', 0)), float(s.get('avg', 0)), float(
            s.get('ops', 0))
        iso, k_pct = slg - avg, (float(s.get('strikeOuts', 0)) / max(float(s.get('plateAppearances', 1)), 1))
        matchup = (float(s.get('wOBA', 0)) * 500) + (iso * 1000)

        return {
            "Hitter": p_data['fullName'], "Team": team_name, "Hand": b_hand,
            "Opp Pitcher": p_met.get('Name', 'TBD'), "Opp Pitcher Hand": p_met.get('Hand', 'R'),
            "Advantage": "Advantage" if b_hand != p_met.get('Hand') else "Disadvantage",
            "HR": hr, "Hits": float(s.get('hits', 0)), "TB": float(s.get('totalBases', 0)),
            "AVG": avg, "OPS": ops, "SLG": slg, "ISO": iso, "K%": k_pct, "Matchup": matchup
        }
    except:
        return None


def style_df(data):
    cols = ["Hitter", "Team", "Hand", "Opp Pitcher", "Opp Pitcher Hand", "Advantage", "HR", "Hits", "TB", "AVG", "OPS",
            "SLG", "ISO", "K%", "Matchup"]
    display_df = data[[c for c in cols if c in data.columns]]
    return display_df.style.format({
        "HR": "{:.1f}", "Hits": "{:.1f}", "TB": "{:.1f}", "AVG": "{:.3f}",
        "OPS": "{:.3f}", "SLG": "{:.3f}", "ISO": "{:.3f}", "Matchup": "{:.1f}", "K%": "{:.1%}"
    }).map(lambda x: {'Advantage': 'background-color: #d4edda', 'Disadvantage': 'background-color: #f8d7da'}.get(x, ''),
           subset=['Advantage']) \
        .background_gradient(cmap="RdYlGn", subset=["HR", "Hits", "TB", "AVG", "OPS", "SLG", "ISO", "Matchup"]) \
        .background_gradient(cmap="RdYlGn_r", subset=["K%"])


# --- MAIN EXECUTION ---
sched = fetch_mlb_data("https://statsapi.mlb.com/api/v1/schedule",
                       {"sportId": 1, "date": today, "hydrate": "probablePitcher"})
master_list, data_source_mode = [], "Confirmed (Official Lineups)"

if 'dates' in sched and len(sched['dates']) > 0:
    for game in sched['dates'][0]['games']:
        game_id = game['gamePk']
        boxscore = fetch_mlb_data(f"https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore")

        h_met = get_pitcher_metrics(game['teams']['home'].get('probablePitcher', {}).get('id'))
        a_met = get_pitcher_metrics(game['teams']['away'].get('probablePitcher', {}).get('id'))

        use_roster = not (boxscore and 'teams' in boxscore and boxscore['teams']['home'].get('battingOrder'))
        if use_roster: data_source_mode = "Estimated (Full Active Roster - Lineups Pending)"

        for team_key, p_met in [('away', h_met), ('home', a_met)]:
            team_id = game['teams'][team_key]['team']['id']
            team_name = game['teams'][team_key]['team']['name']

            starters = boxscore['teams'][team_key].get('battingOrder', []) if not use_roster else [p['person']['id'] for
                                                                                                   p in fetch_mlb_data(
                    f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster/Active?hydrate=person").get('roster', [])
                                                                                                   if p.get('position',
                                                                                                            {}).get(
                    'abbreviation') != 'P']

            for pid in starters:
                p_info = fetch_mlb_data(f"https://statsapi.mlb.com/api/v1/people/{pid}")
                b_hand = p_info['people'][0].get('batSide', {}).get('code', 'R') if (
                            p_info and 'people' in p_info) else 'R'
                hitter = get_hitter_stats(pid, p_met, b_hand, team_name)
                if hitter: master_list.append(hitter)

    df_all = pd.DataFrame(master_list)
    st.info(f"Source Mode: {data_source_mode}")

    # --- TOP 5 LEADERS ---
    st.header("🏆 Matchup-Based Daily Leaders (Top 5)")
    c1, c2, c3 = st.columns(3)
    c1.subheader("Top Matchups");
    c1.dataframe(df_all.sort_values("Matchup", ascending=False).head(5).round(1), hide_index=True)
    c2.subheader("Advantage Hitters");
    c2.dataframe(df_all[df_all['Advantage'] == 'Advantage'].nlargest(5, "Matchup").round(1), hide_index=True)
    c3.subheader("High ISO Leaders");
    c3.dataframe(df_all.nlargest(5, "ISO").round(1), hide_index=True)

    # --- FULL SLATE VALIDATION ---
    st.header("🏟️ Full Slate Validation")
    for game in sched['dates'][0]['games']:
        away, home = game['teams']['away']['team']['name'], game['teams']['home']['team']['name']
        a_met = get_pitcher_metrics(game['teams']['away'].get('probablePitcher', {}).get('id'))
        h_met = get_pitcher_metrics(game['teams']['home'].get('probablePitcher', {}).get('id'))

        with st.expander(f"{away} @ {home}", expanded=True):
            st.markdown(
                f"✈️ **Away Pitcher ({a_met['Name']}):** Hand: {a_met['Hand']} | K/9: {a_met['K/9']:.1f} | HR/9: {a_met['HR/9']:.1f} | ERA: {a_met['ERA']:.2f} | WHIP: {a_met['WHIP']:.2f} | OBA: {a_met['OBA']:.3f}")
            st.markdown(
                f"🏠 **Home Pitcher ({h_met['Name']}):** Hand: {h_met['Hand']} | K/9: {h_met['K/9']:.1f} | HR/9: {h_met['HR/9']:.1f} | ERA: {h_met['ERA']:.2f} | WHIP: {h_met['WHIP']:.2f} | OBA: {h_met['OBA']:.3f}")

            t1, t2 = st.tabs(["✈️ Away Offense", "🏠 Home Offense"])
            with t1: st.dataframe(style_df(df_all[df_all['Team'] == away]), use_container_width=True)
            with t2: st.dataframe(style_df(df_all[df_all['Team'] == home]), use_container_width=True)
else:
    st.warning("No games found for today.")