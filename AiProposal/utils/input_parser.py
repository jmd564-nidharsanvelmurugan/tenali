def input_parser(questions: list, answers: list) -> dict:
    user_input = {}
    for i in range(len(questions)):
        if questions[i].get('category') == 'GENERAL':
            continue

        value = list(map(lambda a: a.strip(), answers[i].split(",")))
        category = questions[i]['category'].lower()

        if len(value) == 1:
            if category == "project_type" and value[0].lower() == "both":
                user_input[category] = ["design and discovery", "build"]
            elif category == "existing_infra" and value[0].lower() == "yes":
                user_input[category] = ["has data platform"]
            else:
                user_input[category] = [value[0].lower()]            
        elif len(value) >1:
            user_input[category] = [v.lower() for v in value]

    return user_input

