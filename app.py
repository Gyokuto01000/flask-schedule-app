from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# イベントデータ（メモリに保持、後でDBに変更可）
events = {}

# 参加者データ（後でDBに変更可）
participants = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        event_name = request.form['event_name']
        date_options = request.form['date_options'].split(',')  # カンマ区切りで日程をリストに
        event_id = event_name.lower().replace(" ", "_")
        
        # イベントの保存
        events[event_id] = {'event_name': event_name, 'date_options': date_options}
        
        return redirect(url_for('poll', event_id=event_id))
    
    return render_template('index.html')

@app.route('/poll/<event_id>', methods=['GET', 'POST'])
def poll(event_id):
    event = events.get(event_id)
    if event is None:
        return "イベントが見つかりません", 404
    
    if request.method == 'POST':
        participant_name = request.form['name']
        selected_dates = request.form.getlist('dates')
        
        # 参加者データを保存（名前と選んだ日程）
        participants[participant_name] = {
            'event_id': event_id,
            'selected_dates': selected_dates
        }
        
        return redirect(url_for('results', event_id=event_id))
    
    return render_template('poll.html', event=event)

@app.route('/results/<event_id>')
def results(event_id):
    event = events.get(event_id)
    if event is None:
        return "イベントが見つかりません", 404
    
    # 参加者ごとに選んだ日程を集計
    selected_dates = {date: [] for date in event['date_options']}  # 候補日程をキーとして空のリストを用意
    
    for participant, data in participants.items():
        if data['event_id'] == event_id:
            for date in data['selected_dates']:
                selected_dates[date].append(participant)  # 各日程に対する参加者をリストに追加
    
    return render_template('results.html', event=event, selected_dates=selected_dates)

if __name__ == '__main__':
    app.run(debug=True)
