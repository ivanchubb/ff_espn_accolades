#! /usr/bin/python3

import datetime
import secrets
from espn_api.football import League
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError
from flask import Flask, request, render_template, flash, session

app = Flask(__name__, template_folder="templates")
secret = secrets.token_urlsafe(32)
app.secret_key = secret
""" def find_optimal_players_for_position(players: list, slot: str) -> League.BoxPlayer:
    Return a list of players with the highest points for a given slot.
"""

class Accolade:

    def __init__(self, title, team, points):
        self.title = title
        self.team = team
        self.points = points
        self.opp_score = 0
        self.effeciency = 0
        self.projected = 0
        self.opponent = None
        self.optimal_score = 0
        self.player = None

    def __repr__(self):
        return self.points

def get_season_start(year):
    """Returns the start date of the season for the given year."""
    # Assuming the NFL season will start from September 4th or later.
    date = datetime.datetime(year, 9, 4)
    
    # Find the next Thursday.
    while date.weekday() != 3:  # 3 stands for Thursday
        date += datetime.timedelta(days=1)
    
    return date

def get_current_week():
    """Returns the current NFL week."""
    today = datetime.datetime.today()
    
    # If the current date is before this year's season start, 
    # consider the end of the previous season.
    if today < get_season_start(today.year):
        start_date = get_season_start(today.year - 1)
    else:
        start_date = get_season_start(today.year)
    
    days_since_start = (today - start_date).days
    current_week = (days_since_start // 7) + 1

    # Ensure the week is capped at 17, in case the current date goes beyond the regular season.
    return min(current_week, 17)

def get_best_by_skill(lineup_copy: list, slot: str):
    """ gets the best player for a given slot from the provided list of players"""
    # turns FLEX like "RB/WR/TE" to ["RB", "WR", "TE"]
    eligible_players = [
        p for p in lineup_copy
        if slot in p.eligibleSlots
        and p.game_played == 100
        and not p.on_bye_week
    ]

    try:
        best_available = sorted(eligible_players, key=lambda x: x.points)[-1]
    except IndexError:
        # print(f"No eligible players for: {slot}")
        return []
    lineup_copy.remove(best_available)

    return best_available


def get_optimal_lineup(lineup: list) -> float:
    """Compute the difference between optimal lineup and current lineup."""
    optimal_lineup = []
    lineup_slots = []
    for i in lineup:
        lineup_slots.append(i.slot_position)

    lineup_slots = [item for item in lineup_slots if item not in ("BE", "IR")]

    # ensures that main positions (ex: "RB") get priority over FLEX ones (ex: "WR/RB")
    lineup_slots = sorted(lineup_slots, key=len)

    # a bit hacky, but superflex has to be last
    if "OP" in lineup_slots:
        lineup_slots.remove("OP")
        lineup_slots.append("OP")

    lineup_copy = lineup.copy()

    for slot in lineup_slots:
        optimal_lineup.append(get_best_by_skill(lineup_copy, slot))

    optimal_score = 0
    for x in optimal_lineup:
        try:
            optimal_score += x.points
        except AttributeError:
            continue
    
    return optimal_score

def get_team_awards(box_scores: list):
    """ gets the team based performance awards"""
    dominant_winner = Accolade("Most Dominant Win", box_scores[0].home_team, 0)
    narrowest_winner = Accolade("Closest Win", box_scores[0].home_team, 9999)
    highest_loser = Accolade("Toughest Loss", box_scores[0].home_team, 0)
    lowest_winner = Accolade("Luckiest Win", box_scores[0].home_team, 9999)
    highest_scorer = Accolade("Highest Scorer", box_scores[0].home_team, 0)
    lowest_scorer = Accolade("Lowest Scorer", box_scores[0].home_team, 9999)

    for matchup in box_scores:
        home_team = matchup.home_team
        away_team = matchup.away_team
        home_score = matchup.home_score
        away_score = matchup.away_score

        # Determine winner and loser for the matchup
        if home_score > away_score:
            winner, loser = home_team, away_team
            winning_score, losing_score = home_score, away_score
        else:
            winner, loser = away_team, home_team
            winning_score, losing_score = away_score, home_score

        score_diff = abs(home_score - away_score)

        # Check for biggest win
        if score_diff > (dominant_winner.points - dominant_winner.opp_score):
            dominant_winner.team = winner
            dominant_winner.points = winning_score
            dominant_winner.opp_score = losing_score
            dominant_winner.opponent = loser

        # Check for narrowest win
        if score_diff < (narrowest_winner.points - narrowest_winner.opp_score):
            narrowest_winner.team = winner
            narrowest_winner.points = winning_score
            narrowest_winner.opp_score = losing_score
            narrowest_winner.opponent = loser

        # Check for highest scoring loser
        if losing_score > highest_loser.points:
            highest_loser.team = loser
            highest_loser.points = losing_score
            highest_loser.opp_score = winning_score
            highest_loser.opponent = winner

        # Check for lowest scoring winner
        if winning_score < lowest_winner.points:
            lowest_winner.team = winner
            lowest_winner.points = winning_score
            lowest_winner.opp_score = losing_score
            lowest_winner.opponent = loser

        # highest scorer
        if winning_score > highest_scorer.points:
            highest_scorer.team = winner
            highest_scorer.points = winning_score

        # highest scorer
        if losing_score < lowest_scorer.points:
            lowest_scorer.team = loser
            lowest_scorer.points = losing_score

    return [dominant_winner,
            narrowest_winner,
            highest_loser,
            lowest_winner,
            highest_scorer,
            lowest_scorer]

def get_lineup_awards(box_scores):

    best_manager = Accolade("Best Manager", None, 0)
    worst_manager = Accolade("Worst Manager", None, 9999)

    effeciency_dict = {}
    for matchup in box_scores:
        effeciency_dict[matchup.home_team] = get_roster_effeciency(matchup.home_lineup,
                                                                   matchup.home_score)
        effeciency_dict[matchup.away_team] = get_roster_effeciency(matchup.away_lineup,
                                                                   matchup.away_score)

    best_manager.team = max(effeciency_dict, key=lambda k: effeciency_dict[k][2])
    best_manager.points = effeciency_dict[best_manager.team][0]
    best_manager.optimal_score = effeciency_dict[best_manager.team][1]
    best_manager.effeciency = effeciency_dict[best_manager.team][2]

    worst_manager.team = min(effeciency_dict, key=lambda k: effeciency_dict[k][2])
    worst_manager.points = effeciency_dict[worst_manager.team][0]
    worst_manager.optimal_score = effeciency_dict[worst_manager.team][1]
    worst_manager.effeciency = effeciency_dict[worst_manager.team][2]

    return [best_manager, worst_manager]

def get_player_awards(box_scores):

    boom_player = Accolade("Biggest Boom", box_scores[0].home_team, 0)
    bust_player = Accolade("Biggest Bust", box_scores[0].home_team, 999)
    mistake_player = Accolade("Biggest Mistake", box_scores[0].home_team, 999)

    for matchup in box_scores:
        for lineup in [matchup.home_lineup, matchup.away_lineup]:

            played_players = [player for player in lineup if player.slot_position not in ["BE", "IR"]]
            benched_players = [player for player in lineup if player.slot_position == "BE"]

            # Calculate boom and bust as before
            for player in played_players:
                performance = player.points - player.projected_points
                if performance > boom_player.points:
                    boom_player.player = player
                    boom_player.points = performance
                    if player in matchup.home_lineup:
                        boom_player.team = matchup.home_team
                    else:
                        boom_player.team = matchup.away_team
                if performance < bust_player.points:
                    bust_player.player = player
                    bust_player.points = performance
                    if player in matchup.home_lineup:
                        bust_player.team = matchup.home_team
                    else:
                        bust_player.team = matchup.away_team

            # Calculate biggest mistake
            for benched_player in benched_players:
                position_mates = [player for player in played_players if player.slot_position in benched_player.eligibleSlots]
                if position_mates:  # There must be a played player of the same position
                    lowest_scoring_mate = min(position_mates, key=lambda x: x.points)
                    mistake_value = lowest_scoring_mate.points - benched_player.points
                    if mistake_value < mistake_player.points:
                        mistake_player.player = lowest_scoring_mate
                        mistake_player.points = mistake_value
                        mistake_player.benched_player = benched_player
                        if benched_player in matchup.home_lineup:
                            mistake_player.team = matchup.home_team
                        else:
                            mistake_player.team = matchup.away_team

    return [boom_player, bust_player, mistake_player]


def get_accolades(box_scores: list):
    """ gets all the the accolades"""
    awards = get_team_awards(box_scores)
    awards += get_lineup_awards(box_scores)
    awards += get_player_awards(box_scores)

    return awards


def get_roster_effeciency(lineup, score):
    """ gets the roster effeciency"""
    optimal_score = round(get_optimal_lineup(lineup), 2)
    try:
        effeciency = round(score / optimal_score, 2)
    except ZeroDivisionError:
        effeciency = 0
    return (score, optimal_score, effeciency)

def prepare_card(accolade):

    try:
        opp_name = accolade.opponent.team_name
    except AttributeError:
        opp_name = ""

    try:
        player_points = accolade.player.points
        player_proj_points = accolade.player.projected_points
        player_name = accolade.player.name
    except AttributeError:
        player_points = 0
        player_proj_points = 0
        player_name = ""

    try:
        benched_player = accolade.benched_player.name
        benched_points = accolade.benched_player.points
    except AttributeError:
        benched_points = 0
        benched_player = ""

    diff_score = accolade.points - accolade.opp_score
    team_name = accolade.team.team_name
    eff_score = accolade.effeciency * 100
    optimal = accolade.optimal_score

    boom_diff = player_points - player_proj_points
    bust_diff = player_proj_points - player_points

    subtitles = {
        "Most Dominant Win": f"{team_name} dominated '{opp_name}' by {diff_score:.2f} points!",
        "Closest Win": f"{team_name} beat '{opp_name}' by just {diff_score:.2f} points",
        "Toughest Loss": f"{team_name} scored more than any other loser",
        "Luckiest Win": f"{team_name} scored less than any other winner",
        "Highest Scorer": "👑"*10,
        "Lowest Scorer": "💩"*10,
        "Best Manager": f"{team_name} scored {eff_score:.2f}% of their possible {optimal:.2f} points!",
        "Worst Manager": f"{team_name} scored {eff_score:.2f}% of their possible {optimal:.2f} points.",
        "Biggest Boom": f"{team_name} started {player_name}, the player of the week,"
                        f" scoring {boom_diff:.2f} more than projected!",
        "Biggest Bust": f"{team_name} started {player_name}, the bust of the week,"
                        f" scoring {bust_diff:.2f} less than projected!",
        "Biggest Mistake": f"{team_name} started {player_name} ({player_points:.2f} points), instead of {benched_player} ({benched_points:.2f} points)."
    }
    emoji_dict = {
    "Most Dominant Win": "💪",
    "Closest Win": "😅",
    "Toughest Loss": "💔",
    "Luckiest Win": "🍀",
    "Highest Scorer": "👑",
    "Lowest Scorer": "💩",
    "Best Manager": "🌟",
    "Worst Manager": "🌮",
    "Biggest Boom": "💥",
    "Biggest Bust": "📉",
    "Biggest Mistake": "🤡"
    }


    card = {
        "title": emoji_dict[accolade.title] + " " + accolade.title,  # Assuming accolade always has a title.
        "subtitle": subtitles.get(accolade.title, ""),
        "image": getattr(accolade.team, 'logo_url', None),
        "middle_text": getattr(accolade.team, 'team_name', ""),
        "middle_sub_text": None,
        "middle_sub_sub_text": None,
        "points": round(accolade.points, 2)  # Assuming accolade always has points.
    }

    # overrides for player cards
    if ("Boom" in accolade.title or "Bust" in accolade.title):
        card["middle_text"] = player_name
        try:
            card["middle_sub_text"] = f"{accolade.player.position} - {accolade.player.proTeam}"
            card["points"] = round(accolade.player.points, 2)
            if accolade.player.position != "D/ST":
                card["image"] = f"https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{accolade.player.playerId}.png"
            else:
                card["image"] = f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/{accolade.player.proTeam}.png"
        except AttributeError:
            card["middle_sub_text"] = ""
            card["points"] = ""
        
    return card

@app.route('/', methods=['GET', 'POST'])
def index():
    cards_data = []
    current_week = get_current_week()

    if request.method == 'POST':
        league_id = request.form.get('league_id')
        user_swid = request.form.get('swid')
        user_espn_s2 = request.form.get('espn_s2')
        try:
            week = int(request.form.get('week'))
            if week > 17 or week < 1:
                raise ValueError
        except ValueError:
            flash(f"Please provide a week between 1 and 17")
            return render_template("accolades.html", current_week=current_week)
        if league_id and week:
            try:
                flash("Getting league data...", category="progress")
                # accounts for games in January or lookups after the season
                # TODO: add past season lookups with an optional year field
                year = datetime.date.today().year
                if datetime.date.today().month < 7:
                    year -= 1
                league = League(league_id, year,swid=user_swid, espn_s2=user_espn_s2, debug=False)
            except ESPNAccessDenied as e:
                session.pop('_flashes', None)
                flash(f"League ID: {league_id} isn't set to public or you entered the wrong (SWID/S2 value).", category="progress")
                return render_template("accolades.html", current_week=current_week)
            except ESPNInvalidLeague as e:
                session.pop('_flashes', None)
                flash(e.args[0], category="progress")
                return render_template("accolades.html", current_week=current_week)
            except ESPNUnknownError as e:
                session.pop('_flashes', None)
                flash(f"{e.args[0]}, ensure your League ID is correct", category="progress")
                return render_template("accolades.html", current_week=current_week)
                
            weekly_scores = league.box_scores(week)

            flash("Calculating accolades...", category="progress")
            accolades = get_accolades(weekly_scores)

            cards_data = [prepare_card(accolade) for accolade in accolades]
            session.pop('_flashes', None)

            return render_template("accolades.html", cards_data=cards_data, current_week=current_week)
        else:
            flash("Please fill out all fields", category="progress")

    
    return render_template("accolades.html", current_week=current_week)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)

