from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import datetime
import jpholiday

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # フラッシュメッセージ用

# PostgreSQL想定。Renderの環境変数DATABASE_URLを使う
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///events.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_options = db.Column(db.String(500), nullable=False)  # カンマ区切りの日付文字列
    questions = db.relationship('Question', backref='event', cascade='all, delete-orphan')
    participants = db.relationship('Participant', backref='event', cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    text = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'text', 'radio', 'checkbox'
    options = db.relationship('QuestionOption', backref='question', cascade='all, delete-orphan')

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(100), nullable=False)

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    selected_dates = db.Column(db.String(200), nullable=False)  # カンマ区切り
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    answers = db.relationship('ParticipantAnswer', backref='participant', cascade='all, delete-orphan')

class ParticipantAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_text = db.Column(db.Text, nullable=True)


with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/events')
def events():
    all_events = Event.query.order_by(Event.id.desc()).all()
    return render_template('events_list.html', events=all_events)

@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == 'POST':
        event.name = request.form['event_name'].strip()
        event.date_options = request.form['date_options'].strip()
        db.session.commit()
        flash('イベントを更新しました！', 'success')
        return redirect(url_for('events'))
    return render_template('edit_event.html', event=event)

@app.route('/events/<int:event_id>')
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    questions = event.questions

    # 日付の参加者集計
    date_participants_map = {}
    for d_str in event.date_options.split(','):
        d_str = d_str.strip()
        if not d_str:
            continue
        date_participants_map[d_str] = []

    for p in event.participants:
        for d in p.selected_dates.split(','):
            d = d.strip()
            if d in date_participants_map:
                date_participants_map[d].append(p.name)

    # 参加者ごとの回答を整形
    participant_answers = []
    for p in event.participants:
        answers = {}
        for ans in p.answers:
            answers[ans.question_id] = ans.answer_text
        participant_answers.append({
            'name': p.name,
            'selected_dates': p.selected_dates.split(','),
            'answers': answers
        })

    # 最多投票の参加日を取得
    max_participation_count = 0
    most_selected_dates = []
    for d, participants_list in date_participants_map.items():
        count = len(participants_list)
        if count > max_participation_count:
            max_participation_count = count
            most_selected_dates = [d]
        elif count == max_participation_count:
            most_selected_dates.append(d)

    # 質問ごとの最多回答を算出（ラジオ・チェックボックスのみ）
    from collections import Counter
    question_most_answers = {}
    for q in questions:
        if q.type not in ['radio', 'checkbox']:
            continue
        answers_for_q = []
        for p_ans in participant_answers:
            ans = p_ans['answers'].get(q.id)
            if not ans:
                continue
            if q.type == 'checkbox':
                answers_for_q.extend([a.strip() for a in ans.split(',')])
            else:
                answers_for_q.append(ans.strip())
        if answers_for_q:
            counter = Counter(answers_for_q)
            max_count = max(counter.values())
            most_answers = [ans for ans, cnt in counter.items() if cnt == max_count]
            question_most_answers[q.id] = most_answers
        else:
            question_most_answers[q.id] = []

    return render_template("event_detail.html", 
                           event=event,
                           questions=questions,
                           participant_answers=participant_answers,
                           most_selected_dates=most_selected_dates,
                           question_most_answers=question_most_answers)



@app.route('/events/delete', methods=['POST'])
def delete_events():
    event_ids = request.form.getlist('event_ids')
    if not event_ids:
        flash('削除するイベントを選択してください。', 'warning')
        return redirect(url_for('events'))
 
    for eid in event_ids:
        event = Event.query.get(eid)
        if event:
            db.session.delete(event)
    db.session.commit()
    flash(f'{len(event_ids)}件のイベントを削除しました。', 'success')
    return redirect(url_for('events'))

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        event_name = request.form['event_name']
        date_options = request.form['date_options'].split(',')
        date_options = [d.strip() for d in date_options if d.strip()]
        event = Event(name=event_name, date_options=','.join(date_options))
        db.session.add(event)
        db.session.flush()  # idを取得したいのでflush

        # 質問と選択肢を保存
        question_texts = request.form.getlist('question_text')
        question_types = request.form.getlist('question_type')
        # 選択肢は"options_{index}"に複数の選択肢がカンマ区切りで入っている
        for i, (q_text, q_type) in enumerate(zip(question_texts, question_types)):
            q_text = q_text.strip()
            q_type = q_type.strip()
            if not q_text:
                continue
            question = Question(event_id=event.id, text=q_text, type=q_type)
            db.session.add(question)
            db.session.flush()
            options_raw = request.form.get(f'options_{i}', '').strip()
            if q_type in ['radio', 'checkbox'] and options_raw:
                options = [opt.strip() for opt in options_raw.split(',') if opt.strip()]
                for opt_text in options:
                    option = QuestionOption(question_id=question.id, text=opt_text)
                    db.session.add(option)

        db.session.commit()
        flash('イベントを作成しました！', 'success')
        return redirect(url_for('poll', event_id=event.id))

    return render_template('create.html')

def parse_answers_from_form(form):
    answers = {}
    for key in form:
        if key.startswith("question_"):
            value = form.getlist(key)
            answers[key] = value
    return answers

@app.route('/poll/<int:event_id>', methods=['GET', 'POST'])
def poll(event_id):
    event = Event.query.get_or_404(event_id)
    questions = event.questions

    if request.method == 'POST':
        participant_name = request.form['name'].strip()
        selected_dates = request.form.getlist('dates')
        if not participant_name:
            flash('名前を入力してください', 'danger')
            return redirect(request.url)
        if not selected_dates:
            flash('参加可能な日程を1つ以上選択してください', 'danger')
            return redirect(request.url)

        overwrite_confirm = request.form.get('overwrite_confirm')

        existing_participant = Participant.query.filter_by(event_id=event.id, name=participant_name).first()

        if existing_participant and overwrite_confirm != 'yes':
            form_answers = parse_answers_from_form(request.form)
            return render_template(
                'confirm_overwrite.html',
                event=event,
                participant_name=participant_name,
                selected_dates=selected_dates,
                questions=questions,
                answers=form_answers
            )

        if existing_participant and overwrite_confirm == 'yes':
            # 上書きの場合、まず日付を更新
            existing_participant.selected_dates = ','.join(selected_dates)
            # 既存回答を確実に削除（session.deleteを使う）
            for ans in existing_participant.answers:
                db.session.delete(ans)
            db.session.flush()
            participant = existing_participant
        else:
            participant = Participant(name=participant_name, selected_dates=','.join(selected_dates), event_id=event.id)
            db.session.add(participant)
            db.session.flush()

        # 質問の回答を保存
        for q in questions:
            if q.type == 'checkbox':
                vals = request.form.getlist(f'question_{q.id}')
                if not vals:
                    continue
                answer_val = ','.join(vals)
            else:
                answer_val = request.form.get(f'question_{q.id}')
                if answer_val is None or answer_val == '':
                    continue

            pa = ParticipantAnswer(participant_id=participant.id, question_id=q.id, answer_text=answer_val)
            db.session.add(pa)

        db.session.commit()
        flash('回答を送信しました！', 'success')
        return redirect(url_for('results', event_id=event.id))

    # 日付に曜日・祝日付加
    weekdays = "月火水木金土日"
    display_dates = []
    for d_str in event.date_options.split(','):
        d_str = d_str.strip()
        if not d_str:
            continue
        try:
            d_obj = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
            w = weekdays[d_obj.weekday()]
            holiday_name = jpholiday.is_holiday_name(d_obj)
            label = f"{d_str}（{w}）"
            if holiday_name:
                label += f" 🎌{holiday_name}"
            display_dates.append({'value': d_str, 'label': label})
        except:
            continue

    return render_template('poll.html', event=event, display_dates=display_dates, questions=questions)



from collections import Counter

@app.route('/results/<int:event_id>')
def results(event_id):
    event = Event.query.get_or_404(event_id)
    questions = event.questions

    
    
    # 日付の参加者集計
    date_participants_map = {}
    for d_str in event.date_options.split(','):
        d_str = d_str.strip()
        if not d_str:
            continue
        date_participants_map[d_str] = []

    for p in event.participants:
        for d in p.selected_dates.split(','):
            d = d.strip()
            if d in date_participants_map:
                date_participants_map[d].append(p.name)

    # 参加者ごとの回答を整形
    participant_answers = []
    for p in event.participants:
        answers = {}
        for ans in p.answers:
            answers[ans.question_id] = ans.answer_text
        participant_answers.append({
            'name': p.name,
            'selected_dates': p.selected_dates.split(','),
            'answers': answers
        })

    # 最多投票の参加日を取得
    max_participation_count = 0
    most_selected_dates = []
    for d, participants_list in date_participants_map.items():
        count = len(participants_list)
        if count > max_participation_count:
            max_participation_count = count
            most_selected_dates = [d]
        elif count == max_participation_count:
            most_selected_dates.append(d)

    # 質問ごとの最多回答を算出（ラジオ・チェックボックスのみ）
    question_most_answers = {}
    for q in questions:
        if q.type not in ['radio', 'checkbox']:
            continue
        # 回答を集計
        answers_for_q = []
        for p_ans in participant_answers:
            ans = p_ans['answers'].get(q.id)
            if not ans:
                continue
            if q.type == 'checkbox':
                # 複数回答はカンマ区切りなので分割
                answers_for_q.extend([a.strip() for a in ans.split(',')])
            else:
                answers_for_q.append(ans.strip())
        if answers_for_q:
            counter = Counter(answers_for_q)
            max_count = max(counter.values())
            # 最多回答（複数ある場合はリスト）
            most_answers = [ans for ans, cnt in counter.items() if cnt == max_count]
            question_most_answers[q.id] = most_answers
        else:
            question_most_answers[q.id] = []

    # 日付に曜日・祝日付加
    weekdays = "月火水木金土日"
    display_dates = []
    for d_str in event.date_options.split(','):
        d_str = d_str.strip()
        if not d_str:
            continue
        try:
            d_obj = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
            w = weekdays[d_obj.weekday()]
            holiday_name = jpholiday.is_holiday_name(d_obj)
            label = f"{d_str}（{w}）"
            if holiday_name:
                label += f" 🎌{holiday_name}"
            display_dates.append({'value': d_str, 'label': label})
        except:
            display_dates.append({'value': d_str, 'label': d_str})

        available_dates = [d.strip() for d in event.date_options.split(',') if d.strip()]

    return render_template('results.html', event=event, questions=questions,
                           date_participants_map=date_participants_map,
                           participant_answers=participant_answers,
                           display_dates=display_dates,
                           most_selected_dates=most_selected_dates,
                           question_most_answers=question_most_answers,
                           date_participants=date_participants_map,
                           available_dates=available_dates )


if __name__ == '__main__':
    app.run(debug=True)