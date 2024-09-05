# hardsize

This script substitutes Autosize fields with hard sizes (capacity, flow rate, or volume) taken from a SQL database file with sizing data from a previous run.

The script looks for epJSON files in the same folder and if there is a .sql file with the same name, it will run the script on the epJSON using the .sql file to lookup sizes.

The script relies on a CSV file (22-1.csv), unique for each version of EnergyPlus, which is a lookup table used to translate the field name in the SQL file corresponding to the field description in the epJSON.

The script can also be used to alter sizing values for particular objects/classes using the alter_sizing function.