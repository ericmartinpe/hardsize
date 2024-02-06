import os, sqlite3, json, csv

# generate a dictionary of ep classes with fields descriptions/keys per SQL and epJSON
# {"AirLoopHVAC" : [["Design Supply Air Flow Rate", "design_supply_air_flow_rate"]],
#  "AirTerminal:SingleDuct:VAV:Reheat" : [["Design Size Constant Minimum Air Flow Fraction", "constant_minimum_air_flow_fraction"],
#                                           ["Design Size Maximum Air Flow Rate", "maximum_air_flow_rate"]]}
def gen_fields_dict(csv_file):
    fields_dict = {}
    with open(csv_file, mode ='r') as file:
        csvFile = csv.reader(file)
        for row in csvFile:
            if row[0] in fields_dict.keys():
                fields_dict[row[0]].append([row[1], row[2]])
            else:
                fields_dict[row[0]] = [[row[1], row[2]]]
        return fields_dict

def hardsize_epjson(ep_json, sql_db, fields_dict, output_epjson):
    with open(ep_json) as f:
        ep_model = json.load(f)

    # First, remove Sizing: objects and update ep_model["SimulationControl"]["SimulationControl 1"]
    sizing_classes = {
        "Sizing:System" : "do_system_sizing_calculation",
        "Sizing:Plant" : "do_plant_sizing_calculation"
    }
    for c in sizing_classes.keys():
        if c in ep_model.keys():
            del ep_model[c]
            ep_model["SimulationControl"]["SimulationControl 1"][sizing_classes[c]] = "No"

    db = sqlite3.connect(sql_db)
    cursor = db.cursor()
    class_query = "SELECT DISTINCT CompType FROM ComponentSizes"
    classes = [item[0] for item in cursor.execute(class_query).fetchall()] # create list of classes in component sizing summary

    # loop over classes in CompType FROM ComponentSizes table (SQL)
    for ep_class in classes:
        # only loop over class if it's in fields_dict (the csv)
        if ep_class in fields_dict.keys():
            # create list of all object names within the class
            object_query = f"SELECT DISTINCT CompName FROM ComponentSizes WHERE CompType='{ep_class}'"
            object_names = [item[0] for item in cursor.execute(object_query).fetchall()] # create list of object names for in each class

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
                            ep_model[ep_class][obj][val[1]] = hardsize
    db.close()
    with open(output_epjson, "w") as f:
        output_epjson = json.dump(ep_model, f, indent = 4)



dir = os.path.dirname(os.path.realpath(__file__))

for path, subdirs, files in os.walk(dir):
    for name in files:
        ext = os.path.splitext(name)[-1].lower()
        if ext == ".epjson":
            epname = name.split(".")[0]
            if os.path.isfile(epname+".sql"):
                hardsize_epjson(epname+".epjson", epname+".sql", gen_fields_dict("22-1.csv"), epname+"_out.epjson")

# sql_file = os.path.join(dir,"in.sql")
# epjson = os.path.join(dir,"in.epJSON")
# output = os.path.join(dir,"out.epJSON")
# fields_csv = os.path.join(dir,"22-1.csv")
#
# hardsize_epjson(epjson, sql_file, gen_fields_dict(fields_csv), output)
