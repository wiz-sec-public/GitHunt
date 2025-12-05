from flask import Flask, jsonify, render_template
from db_utils import get_potential_attacks, get_payloads, get_actors

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/potential_attacks', methods=['GET'])
def potential_attacks_route():
    attacks = get_potential_attacks()
    return jsonify(attacks)

@app.route('/payloads')
def payloads_route():
    payloads_by_actor = get_payloads()
    return render_template('payloads.html', payloads_by_actor=payloads_by_actor)

@app.route('/actors')
def actors_route():
    actors_processed_data, four_o_four_actors = get_actors()
    return render_template('actors.html', actors=actors_processed_data, four_o_four_actors=four_o_four_actors)

if __name__ == '__main__':
    app.run(debug=True)