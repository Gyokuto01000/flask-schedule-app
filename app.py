from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os
import datetime
import jpholiday

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

@app.route('/')
def index():
    return render_template('index.html')

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

    # 曜日と祝日を付加し、日付順に並べる
    weekdays = "月火水木金土日"
    temp_dates = []

    for date_str in event.date_options.split(','):
        try:
            date_obj = datetime.datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            weekday = weekdays[date_obj.weekday()]
            holiday_name = jpholiday.is_holiday_name(date_obj)
            label = f"{date_str.strip()}（{weekday}）"
            if holiday_name:
                label += f" 🎌{holiday_name}"
            temp_dates.append((date_obj, {'value': date_str.strip(), 'label': label}))
        except ValueError:
            continue

    # 日付順にソート
    temp_dates.sort(key=lambda x: x[0])
    display_dates = [item[1] for item in temp_dates]

    return render_template('poll.html', event=event, display_dates=display_dates)


@app.route('/results/<event_id>')
def results(event_id):
    import datetime
    import jpholiday

    event = Event.query.get(event_id)
    if event is None:
        return "イベントが見つかりません", 404

    # 日付を datetime.date 型で扱う
    raw_selected_dates = {}
    for date_str in event.date_options.split(','):
        try:
            date_obj = datetime.datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            raw_selected_dates[date_obj] = []
        except ValueError:
            continue  # 日付として無効ならスキップ

    for participant in event.participants:
        for date_str in participant.selected_dates.split(','):
            try:
                date_obj = datetime.datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                if date_obj in raw_selected_dates:
                    raw_selected_dates[date_obj].append(participant.name)
            except ValueError:
                continue

    # 日付順に並び替えて表示用データを整形
    selected_dates = {}
    weekdays = "月火水木金土日"

    for date_obj in sorted(raw_selected_dates.keys()):
        weekday = weekdays[date_obj.weekday()]
        holiday_name = jpholiday.is_holiday_name(date_obj)
        label = f"{date_obj.strftime('%Y-%m-%d')}（{weekday}）"
        if holiday_name:
            label += f" 🎌{holiday_name}"
        selected_dates[label] = raw_selected_dates[date_obj]

    return render_template('results.html', event=event, selected_dates=selected_dates)

@app.route('/events')
def events():
    events_list = Event.query.all()  # データベースから全てのイベントを取得
    return render_template('events_list.html', events=events_list)

@app.route('/event/<int:event_id>')
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)  # IDでイベントを取得
    return render_template('event_detail.html', event=event)

@app.route('/event/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)

    # 参加者データも一緒に削除
    Participant.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for('events'))

@app.route('/event/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        event.name = request.form['event_name']
        date_options = request.form['date_options']
        event.date_options = ','.join([d.strip() for d in date_options.split(',')])

        db.session.commit()
        return redirect(url_for('events'))

    return render_template('edit_event.html', event=event)


@app.route('/delete_events', methods=['POST'])
def delete_events():
    ids = request.form.getlist('event_ids')
    if ids:
        for event_id in ids:
            event = Event.query.get(event_id)
            if event:
                # 関連する参加者も削除
                Participant.query.filter_by(event_id=event.id).delete()
                db.session.delete(event)
        db.session.commit()
    return redirect(url_for('events'))

if __name__ == '__main__':
    app.run(debug=True)
