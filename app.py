from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# 環境変数からデータベースURLを取得（Renderで提供されるURLを設定）
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///events.db')  # Render上で設定する
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLAlchemyのインスタンスを作成
db = SQLAlchemy(app)

# イベントモデル
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_options = db.Column(db.String(200), nullable=False)

# 参加者モデル
class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    selected_dates = db.Column(db.String(200), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    event = db.relationship('Event', backref=db.backref('participants', lazy=True))

# データベースの作成
with app.app_context():
    db.create_all()



@app.route('/create', methods=['GET', 'POST'])
def create():                  
    if request.method == 'POST':
        event_name = request.form['event_name']
        date_options = request.form['date_options'].split(',')  # カンマ区切りで日程をリストに
        event = Event(name=event_name, date_options=','.join(date_options))
        
        db.session.add(event)
        db.session.commit()
        
        return redirect(url_for('poll', event_id=event.id))
    
    return render_template('create.html')

@app.route('/poll/<event_id>', methods=['GET', 'POST'])
def poll(event_id):
    event = Event.query.get(event_id)
    if event is None:
        return "イベントが見つかりません", 404
    
    if request.method == 'POST':
        participant_name = request.form['name']
        selected_dates = request.form.getlist('dates')
        
        participant = Participant(name=participant_name, selected_dates=','.join(selected_dates), event_id=event.id)
        db.session.add(participant)
        db.session.commit()
        
        return redirect(url_for('results', event_id=event.id))
    
    return render_template('poll.html', event=event)

@app.route('/results/<event_id>')
def results(event_id):
    event = Event.query.get(event_id)
    if event is None:
        return "イベントが見つかりません", 404
    
    # 参加者ごとに選んだ日程を集計
    selected_dates = {date: [] for date in event.date_options.split(',')}  # 候補日程をキーとして空のリストを用意
    
    for participant in event.participants:
        for date in participant.selected_dates.split(','):
            selected_dates[date].append(participant.name)  # 各日程に対する参加者をリストに追加
    
    return render_template('results.html', event=event, selected_dates=selected_dates)

if __name__ == '__main__':
    app.run(debug=True)
