cat > scripts/gen_fake_matches.py <<'PY'
#!/usr/bin/env python3
# scripts/gen_fake_matches.py
import csv, random, datetime
teams = ["Team A","Team B","Team C","Team D","Team E","Team F"]
outcomes = ["home","draw","away"]
with open("data/sample_matches.csv","w",newline="",encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["id","fecha","deporte","liga","home_team","away_team","home_goals","away_goals","market","outcome","odds_home","odds_draw","odds_away"])
    for i in range(300):
        h = random.choice(teams)
        a = random.choice([t for t in teams if t!=h])
        home_goals = random.randint(0,4)
        away_goals = random.randint(0,4)
        if home_goals>away_goals: outcome = "home"
        elif home_goals==away_goals: outcome = "draw"
        else: outcome = "away"
        odds_home = round(1.5 + random.random()*3.0,2)
        odds_draw = round(2.5 + random.random()*1.5,2)
        odds_away = round(1.5 + random.random()*3.0,2)
        fecha = (datetime.datetime.utcnow() - datetime.timedelta(days=random.randint(0,365))).isoformat()+"Z"
        writer.writerow([f"m{i}",fecha,"soccer","TestLeague",h,a,home_goals,away_goals,"1X2",outcome,odds_home,odds_draw,odds_away])
print("Synthetic data generated: data/sample_matches.csv")
PY
chmod +x scripts/gen_fake_matches.py
