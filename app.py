import json
import google.generativeai as genai
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from itertools import zip_longest

app = Flask(__name__)

app.secret_key = os.environ.get('mysecretkey!!', 'ilovemariott')
genai_api_key = os.getenv('GENAI_API_KEY')
if genai_api_key:
    genai.configure(api_key=genai_api_key)
else:
    raise ValueError("API key not found. Please set the 'GENAI_API_KEY' environment variable.")


@app.route('/', methods=['GET', 'POST'])
def index():
    session.clear()

    if request.method == 'POST':
        session['location'] = request.form['location']
        session['people'] = int(request.form['people'])
        session['duration'] = int(request.form['duration'])
        return redirect(url_for('preferences'))
    return render_template('index.html')


@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    people = session.get('people', 1)
    if request.method == 'POST':
        preferences = request.form.getlist('preference')
        session['preferences'] = preferences
        # Call API with preferences and duration
        itineraries = get_itineraries(session['location'], session['preferences'], session['duration'])
        session['itineraries'] = itineraries  # Store itineraries in session
        return redirect(url_for('itineraries_route'))
    return render_template('preferences.html', people=people)

@app.route('/itineraries', methods=['GET', 'POST'])
def itineraries_route():
    itineraries = session.get('itineraries')
    if itineraries is None:
        return redirect(url_for('index'))

    if request.method == 'POST':
        selected = request.form['selected_itinerary']
        session['selected_itinerary'] = int(selected)
        return redirect(url_for('vote'))
    return render_template('itineraries.html', itineraries=itineraries, zip_longest=zip_longest)

@app.route('/vote', methods=['GET', 'POST'])
def vote():
    selected_itinerary = session.get('selected_itinerary')
    if selected_itinerary is None:
        return redirect(url_for('itineraries_route'))
    return redirect(url_for('result'))

@app.route('/result')
def result():
    itineraries = session.get('itineraries')
    selected_itinerary = session.get('selected_itinerary')

    if itineraries is None or selected_itinerary is None:
        return redirect(url_for('index'))

    winning_itinerary = itineraries[selected_itinerary]
    return render_template('result.html', itinerary=winning_itinerary)

def get_itineraries(location, preferences, duration):
    # Prepare the prompt for the AI
    prompt = f"""
    Generate three distinctly different travel itineraries for a group trip to {location} lasting {duration} days.
    The group has the following preferences: {', '.join(preferences)}.
    Each itinerary should include:
    - The itinerary name.
    - The cities to visit.
    - The number of days to spend in each city.
    - For each city, a short paragraph of what to do, places to see

    **Provide ONLY the itineraries in JSON format as a list of dictionaries with keys: 'name', 'cities', 'days', and 'notes'. Do not include any additional text or explanation. The 'notes' should be a list of strings corresponding to each city.**
    """

    model = genai.GenerativeModel("gemini-1.5-pro")

    # Send the prompt to Gemini
    response = model.generate_content(prompt)

    # Parse the response (assuming Gemini returns JSON) it kinda doesnt sometimes
    itineraries_text = response.text
    print("Gemini's Response:", itineraries_text)

    try:
        itineraries = json.loads(itineraries_text)
    except json.JSONDecodeError:
        itineraries = []
        print("Failed to parse itineraries JSON.")

    return itineraries

@app.route('/get_attractions', methods=['POST'])
def get_attractions_route():
    data = request.get_json()
    city = data.get('city')
    user_prompt = data.get('user_prompt')
    if not city:
        return jsonify({'success': False, 'error': 'City not provided'}), 400

    preferences = session.get('preferences', [])

    # gets attractions
    attractions = get_attractions(city, preferences, user_prompt)

    # Add the city to each attraction
    for attraction in attractions:
        attraction['city'] = city

    return jsonify({'success': True, 'attractions': attractions})

def get_attractions(city, preferences, user_prompt=None):
    base_prompt = f"""
    For the city of {city}, list popular attractions that align with the following preferences: {', '.join(preferences)}.
    """

    if user_prompt:
        base_prompt += f"\nUser's specific request: {user_prompt}"

    base_prompt += """
    Provide the attractions in a list of dictionaries with each having:
    - 'name': Name of the attraction.
    - 'description': A brief description.
    - 'category': The category or type of attraction (e.g., museum, park, restaurant).

    **Provide ONLY the attractions in JSON format as a list of dictionaries with keys: 'name', 'description', and 'category'. Do not include any additional text or explanation.**
    """

    prompt = base_prompt.strip()

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)
    attractions_text = response.text
    print(f"Gemini's Response for {city} attractions:", attractions_text)

    try:
        attractions = json.loads(attractions_text)
    except json.JSONDecodeError:
        attractions = []
        print(f"Failed to parse attractions JSON for city: {city}")

    return attractions

@app.route('/regenerate_itinerary', methods=['POST'])
def regenerate_itinerary():
    data = request.get_json()
    itinerary_index = data.get('itinerary_index')
    suggestions = data.get('suggestions')

    # Retrieve itineraries from session
    itineraries = session.get('itineraries', [])

    # Validate itinerary index and suggestions
    if itinerary_index is None or itinerary_index < 0 or itinerary_index >= len(itineraries):
        return jsonify({'success': False, 'error': 'Invalid itinerary index'}), 400

    if not suggestions:
        return jsonify({'success': False, 'error': 'No suggestions provided'}), 400

    # Get the original itinerary
    original_itinerary = itineraries[itinerary_index]

    # Generate a new itinerary based on the original and suggestions
    new_itinerary = regenerate_itinerary_with_suggestions(
        original_itinerary, suggestions, session['location'], session['preferences'], session['duration']
    )

    if new_itinerary:
        # Update the itineraries list and save it back to the session
        itineraries[itinerary_index] = new_itinerary
        session['itineraries'] = itineraries
        return jsonify({'success': True, 'new_itinerary': new_itinerary})
    else:
        return jsonify({'success': False, 'error': 'Failed to regenerate itinerary'}), 500

def regenerate_itinerary_with_suggestions(original_itinerary, suggestions, location, preferences, duration):
    # Prepare the prompt for the AI
    prompt = f"""
    Based on the following original itinerary and the user's suggestions, generate a new itinerary.

    Original Itinerary:
    {json.dumps(original_itinerary)}

    User's Suggestions:
    {suggestions}

    Generate an updated itinerary that incorporates the user's suggestions. Ensure the itinerary remains coherent and suitable for a trip to {location} lasting {duration} days with preferences: {', '.join(preferences)}.

    **Provide ONLY the updated itinerary in JSON format with keys: 'name', 'cities', 'days', and 'notes'. Do not include any additional text or explanation. It should be parseable JSON format. NOTHING ELSE ONLY THE JSON FILE, formatted with the spacing and the brackets right. no '''** 
    """

    model = genai.GenerativeModel("gemini-1.5-pro")

    # Send the prompt to Gemini
    response = model.generate_content(prompt)

    # Parse the response
    itinerary_text = response.text
    print("Gemini's Response:", itinerary_text)

    try:
        new_itinerary = json.loads(itinerary_text)
    except json.JSONDecodeError:
        new_itinerary = None
        print("Failed to parse new itinerary JSON.")

    return new_itinerary

@app.route('/save_attraction', methods=['POST'])
def save_attraction():
    attraction = request.get_json()
    saved_attractions = session.get('saved_attractions', {})

    city = attraction.get('city')
    if city:
        if city not in saved_attractions:
            saved_attractions[city] = {}
        # Use the attraction name as key
        attraction_name = attraction.get('name')
        if attraction_name:
            saved_attractions[city][attraction_name] = attraction
            session['saved_attractions'] = saved_attractions
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Attraction name not provided'}), 400
    else:
        return jsonify({'success': False, 'error': 'City not provided'}), 400

@app.route('/get_saved_attractions', methods=['GET'])
def get_saved_attractions():
    saved_attractions = session.get('saved_attractions', {})
    return jsonify({'success': True, 'saved_attractions': saved_attractions})

def find_optimal_location(city, attractions):
    # Prepare the prompt for Gemini
    attractions_list = ', '.join([attr['name'] for attr in attractions])
    prompt = f"""
    In the city of {city}, given the following attractions: {attractions_list},
    determine the optimal location (e.g., neighborhood or area) that is most centrally located to these attractions.
    Provide only the name of the location.
    """

    model = genai.GenerativeModel("gemini-1.5-pro")

    # Send the prompt to Gemini
    response = model.generate_content(prompt)
    optimal_location = response.text.strip()

    print(f"Optimal location in {city}: {optimal_location}")
    return optimal_location

@app.route('/hotels')
def hotels():
    itineraries = session.get('itineraries')
    selected_itinerary_index = session.get('selected_itinerary')

    if itineraries is None or selected_itinerary_index is None:
        return redirect(url_for('index'))

    itinerary = itineraries[selected_itinerary_index]
    saved_attractions = session.get('saved_attractions', {})

    hotels_data = []
    for city in itinerary['cities']:
        city_attractions = list(saved_attractions.get(city, {}).values())
        optimal_location = find_optimal_location(city, city_attractions)
        hotels = get_hotels_in_area(city, optimal_location)
        hotels_data.append({
            'city_name': city,
            'optimal_location': optimal_location,
            'hotels': hotels
        })

    session['hotels_data'] = hotels_data  # Save hotels data to session
    return render_template('hotels.html', hotels_data=hotels_data)

def get_hotels_in_area(city, area):
    # Placeholder function to simulate fetching hotels
    hotels = [
        {
            'name': f"{area} Hotel 1",
            'address': f"123 {area} Street, {city}",
            'rating': '4.5/5',
            'stars': 4,
            'cost': '$150 per night'
        },
        {
            'name': f"{area} Hotel 2",
            'address': f"456 {area} Avenue, {city}",
            'rating': '4.0/5',
            'stars': 3,
            'cost': '$120 per night'
        },
        {
            'name': f"{area} Hotel 3",
            'address': f"789 {area} Boulevard, {city}",
            'rating': '4.7/5',
            'stars': 5,
            'cost': '$200 per night'
        }
    ]
    return hotels
@app.route('/save_hotels', methods=['POST'])
def save_hotels():
    hotels_data = session.get('hotels_data', [])
    selected_hotels = {}

    for city_data in hotels_data:
        city_name = city_data['city_name']
        selected_index = request.form.get(f'selected_hotel_{city_name}')
        if selected_index is not None:
            selected_hotel = city_data['hotels'][int(selected_index)]
            selected_hotels[city_name] = selected_hotel

    session['selected_hotels'] = selected_hotels
    return redirect(url_for('transportation'))

@app.route('/transportation', methods=['GET', 'POST'])
def transportation():
    if request.method == 'POST':
        selected_modes = []
        for i in range(len(session.get('itinerary_cities', [])) - 1):
            mode = request.form.get(f'transport_mode_{i}')
            selected_modes.append(mode)

        session['selected_transport_modes'] = selected_modes
        return redirect(url_for('final_summary'))

    itinerary = session.get('itineraries')[session.get('selected_itinerary')]
    transport_options = get_transport_options(itinerary['cities'])
    session['itinerary_cities'] = itinerary['cities']
    session['transport_options'] = transport_options  # Save to session

    return render_template('transportation.html', transport_options=transport_options)

def get_transport_options(cities):
    transport_options = []
    for i in range(len(cities) - 1):
        origin = cities[i]
        destination = cities[i + 1]

        # Prepare the prompt for Gemini
        prompt = f"""
        Provide possible transportation modes between {origin} and {destination}, such as 'flight', 'car', 'train'. 
        For each mode, estimate:
        - Time in hours
        - Cost in USD
        - Carbon emissions in kg CO2

        **Provide ONLY the transportation options in JSON format as a list of dictionaries with keys: 'mode', 'time', 'cost', and 'emissions'. Do not include any additional text or explanation.**
        """

        model = genai.GenerativeModel("gemini-1.5-pro")

        # Send the prompt to Gemini
        response = model.generate_content(prompt)

        # Parse the response
        options_text = response.text
        print(f"Gemini's Response for transportation from {origin} to {destination}:", options_text)

        try:
            options = json.loads(options_text)
        except json.JSONDecodeError:
            options = []
            print(f"Failed to parse transportation options JSON for {origin} to {destination}.")

        transport_options.append({
            'origin': origin,
            'destination': destination,
            'options': options
        })

    return transport_options

@app.route('/final_summary')
def final_summary():
    itinerary = session.get('itineraries')[session.get('selected_itinerary')]
    selected_hotels = session.get('selected_hotels', {})
    selected_transport_modes = session.get('selected_transport_modes', [])
    transport_options = session.get('transport_options', [])
    itinerary_cities = session.get('itinerary_cities', [])

    transport_info = []
    total_cost = 0
    total_emissions = 0

    # Build transport_info with cost and emissions
    for i in range(len(itinerary_cities) - 1):
        origin = itinerary_cities[i]
        destination = itinerary_cities[i + 1]
        mode = selected_transport_modes[i]

        # Find the matching transport option to get cost and emissions
        for option in transport_options:
            if option['origin'] == origin and option['destination'] == destination:
                for opt in option['options']:
                    if opt['mode'] == mode:
                        cost = float(opt.get('cost', 0))
                        emissions = float(opt.get('emissions', 0))
                        total_cost += cost
                        total_emissions += emissions

                        transport_info.append({
                            'origin': origin,
                            'destination': destination,
                            'mode': mode,
                            'cost': cost,
                            'emissions': emissions
                        })
                        break

    return render_template(
        'final_summary.html',
        itinerary=itinerary,
        hotels=selected_hotels,
        saved_attractions=session.get('saved_attractions', {}),
        transport_info=transport_info,
        total_cost=total_cost,
        total_emissions=total_emissions
    )
@app.route('/clear_session')
def clear_session():
    session.clear()
    return "Session cleared!"


if __name__ == '__main__':
    app.run(debug=True)
