import os, sqlite3, json, csv

def load_json(file):
    with open(file) as f:
        return json.load(f)

def save_json(dic, file):
    with open(file, "w") as f:
        return json.dump(dic, f, indent = 4)

def del_sizing(ep_model):
    # This function deletes the "Sizing:System" and "Sizing:Plant" classes and changes the "SimulationControl" object accordingly
    sizing_classes = {
        "Sizing:System" : "do_system_sizing_calculation",
        "Sizing:Plant" : "do_plant_sizing_calculation"
    }
    for c in sizing_classes.keys():
        if c in ep_model.keys():
            del ep_model[c]
            ep_model["SimulationControl"]["SimulationControl 1"][sizing_classes[c]] = "No"
    return ep_model

def gen_fields_dict(csv_file):
    """
    This generates a dictionary of ep classes with fields descriptions/keys per SQL and epJSON.
    Each key is an EnergyPlus class, each value is a list.
    The first element in the list is the SQL key, the second element is the corresponding epJSON key for the same field. 
    {"AirLoopHVAC" : [["Design Supply Air Flow Rate", "design_supply_air_flow_rate"]],
    "AirTerminal:SingleDuct:VAV:Reheat" : [["Design Size Constant Minimum Air Flow Fraction", "constant_minimum_air_flow_fraction"],
                                            ["Design Size Maximum Air Flow Rate", "maximum_air_flow_rate"]]}
    """
    fields_dict = {}
    with open(csv_file) as file:
        csvFile = csv.reader(file)
        for row in csvFile:
            if row[0] in fields_dict.keys():
                fields_dict[row[0]].append([row[1], row[2]])
            else:
                fields_dict[row[0]] = [[row[1], row[2]]]
        return fields_dict

def add_to_dict(key, name, field, value, dic):
    '''
    Adds a value to a dictionary.
    '''
    if key not in dic.keys():
        dic[key] = {name : {field : value}}
    elif name not in dic[key].keys():
        dic[key][name] = {field : value}
    elif field not in dic[key][name].keys():
        dic[key][name][field] = value
    return dic

def create_sizing_dict(ep_json, sql_db, fields_dict, output_epjson):
    '''
    This function returns a dictionary (sizing_dict) of equipment sizes (capacities and flow rates).
    Keys are EnergyPlus object classes. Values are a dictionary of {field_description : value}
    {"Coil:Cooling:DX:SingleSpeed": {"gross_rated_total_cooling_capacity" : 5794.31}}
    '''
    db = sqlite3.connect(sql_db)
    cursor = db.cursor()
    class_query = "SELECT DISTINCT CompType FROM ComponentSizes"
    classes = [item[0] for item in cursor.execute(class_query).fetchall()] # create list of classes in component sizing summary

    sizing_dict = {}
    # loop over classes in CompType FROM ComponentSizes table (SQL)
    for ep_class in classes:
        # only loop over class if it's in fields_dict (e.g. 22.1.csv)
        if ep_class in fields_dict.keys():
            # create list of all object names within the class
            object_query = f"SELECT DISTINCT CompName FROM ComponentSizes WHERE CompType='{ep_class}'"
            object_names = [item[0] for item in cursor.execute(object_query).fetchall()] # create list of object names in each class

            # Sometimes the object name in ep_model has different case (upper/lower/camel) than in the sql output file (in sql, all are upper case)
            # Update object_names to match object names in ep_model to ensure match in future operations (so ep_model[[ep_class]][obj] works)
            for key in ep_model[ep_class].keys():
                if key.upper() in object_names:
                    for i, obj in enumerate(object_names):
                        if key.upper() == obj.upper():
                            object_names.remove(obj)
                            object_names.insert(i, key)

            # loop through objects
            for obj in object_names:
                # create list of all fields in object
                field_query = f"SELECT DISTINCT Description FROM ComponentSizes WHERE CompType='{ep_class}' AND CompName='{obj.upper()}'"
                fields = [item[0] for item in cursor.execute(field_query).fetchall()] # create list of field descriptions for each field in class[obj]
                # check if field is in fields_dic
                for val in fields_dict[ep_class]:
                    # val = ["SQL lookup", "field_key"] e.g.: val = ['Design Size Constant Minimum Air Flow Fraction', 'constant_minimum_air_flow_fraction']
                    for field in fields:
                        # check if field is in val and if field is specified/non-blank in ep_model
                        if val[1] in ep_model[ep_class][obj].keys() and field == val[0]:
                            hardsize = cursor.execute(f"SELECT Value FROM ComponentSizes WHERE CompType = '{ep_class}' and CompName = '{obj.upper()}' and Description = '{field}'").fetchone()[0]
                            add_to_dict(ep_class, obj, val[1], hardsize, sizing_dict)

    db.close()
    return sizing_dict

def delete_sizing(ep_model):
    # remove Sizing: objects and update ep_model["SimulationControl"]["SimulationControl 1"]
    sizing_classes = {
        "Sizing:System" : "do_system_sizing_calculation",
        "Sizing:Plant" : "do_plant_sizing_calculation"
    }
    for c in sizing_classes.keys():
        if c in ep_model.keys():
            del ep_model[c]
            ep_model["SimulationControl"]["SimulationControl 1"][sizing_classes[c]] = "No"
    return ep_model

def hardsize_epjson(ep_model, sizing_dict, fields_dict, del_sizing=True):
    if del_sizing:
        delete_sizing(ep_model)

    for ep_class in sizing_dict.keys():
        for obj_name in sizing_dict[ep_class]:
            for field_name in sizing_dict[ep_class][obj_name]:
                ep_model[ep_class][obj_name][field_name] = sizing_dict[ep_class][obj_name][field_name]

    return ep_model

def alter_sizing(sizing_dict, alter_class, alter_field, multiplier):
    if alter_class in sizing_dict.keys():
        for obj in sizing_dict[alter_class].keys():
            if alter_field in sizing_dict[alter_class][obj].keys():
                sizing_dict[alter_class][obj][alter_field] *= multiplier
    return sizing_dict

dir = os.path.dirname(os.path.realpath(__file__))
for filename in os.listdir(dir):
    name, ext = os.path.splitext(filename)
    if ext.lower() == ".epjson":
        ep_model = load_json(filename)
        output_filename = name + "_out.epJSON"
        if os.path.isfile(name + ".sql"):
            ep_version = list(ep_model["Version"].values())[0]['version_identifier']
            fields_dict_path = os.path.join(dir, "field_dictionaries", f"{ep_version}.csv")
            if not os.path.exists(fields_dict_path):
                exit(f"Fields dictionary for EP version {ep_version} does not exist in {dir}/field_dictionaries")
            fields_dict = gen_fields_dict(fields_dict_path)
            sizing_dict = create_sizing_dict(ep_model, name + ".sql", fields_dict, name + "_out.epjson")
            # print(f"Altering Sizing: {filename}")
            # sizing_dict = alter_sizing(sizing_dict, "Coil:Cooling:DX:SingleSpeed", "gross_rated_total_cooling_capacity", 1.5)
            print(f"Hardsizing: {filename}")
            ep_model = hardsize_epjson(ep_model, sizing_dict, fields_dict)
            print(f"Saving: {output_filename}")
            save_json(ep_model, output_filename)

