# app.py
import sqlite3
import pandas as pd
import streamlit as st
from datetime import date

st.set_page_config(page_title="Local Food Wastage Management", layout="wide")

# ---------- DB helpers ----------
@st.cache_resource
def get_conn():
    # food.db must be in the same folder as app.py
    return sqlite3.connect("food.db", check_same_thread=False)

def run_query(sql, params=None):
    conn = get_conn()
    return pd.read_sql_query(sql, conn, params=params or ())

def run_execute(sql, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    conn.commit()

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")

cities = run_query("SELECT DISTINCT City FROM Providers ORDER BY City;")["City"].tolist()
provider_types = run_query("SELECT DISTINCT Type FROM Providers ORDER BY Type;")["Type"].tolist()
food_types = run_query("SELECT DISTINCT Food_Type FROM Food_Listings ORDER BY Food_Type;")["Food_Type"].tolist()
meal_types = run_query("SELECT DISTINCT Meal_Type FROM Food_Listings ORDER BY Meal_Type;")["Meal_Type"].tolist()

city_filter = st.sidebar.multiselect("City", cities)
ptype_filter = st.sidebar.multiselect("Provider Type", provider_types)
ftype_filter = st.sidebar.multiselect("Food Type", food_types)
mtype_filter = st.sidebar.multiselect("Meal Type", meal_types)

# dynamic WHERE for Food_Listings + Providers
where = []
params = []

if city_filter:
    where.append(f"P.City IN ({','.join(['?']*len(city_filter))})")
    params += city_filter
if ptype_filter:
    where.append(f"P.Type IN ({','.join(['?']*len(ptype_filter))})")
    params += ptype_filter
if ftype_filter:
    where.append(f"F.Food_Type IN ({','.join(['?']*len(ftype_filter))})")
    params += ftype_filter
if mtype_filter:
    where.append(f"F.Meal_Type IN ({','.join(['?']*len(mtype_filter))})")
    params += mtype_filter

where_sql = ("WHERE " + " AND ".join(where)) if where else ""

# ---------- Overview ----------
st.title("Local Food Wastage Management System")

colA, colB, colC, colD = st.columns(4)
cards = run_query("""
SELECT
  (SELECT COUNT(*) FROM Providers) AS providers,
  (SELECT COUNT(*) FROM Receivers) AS receivers,
  (SELECT COUNT(*) FROM Food_Listings) AS food_items,
  (SELECT COUNT(*) FROM Claims) AS claims;
""").iloc[0]

colA.metric("Providers", int(cards["providers"]))
colB.metric("Receivers", int(cards["receivers"]))
colC.metric("Food Items", int(cards["food_items"]))
colD.metric("Claims", int(cards["claims"]))

st.divider()

# ---------- Filtered Food Listings table ----------
st.subheader("Filtered Food Listings")
filtered = run_query(f"""
SELECT F.Food_ID, F.Food_Name, F.Quantity, F.Expiry_Date,
       F.Provider_ID, P.Name AS Provider_Name, P.Type AS Provider_Type,
       P.City AS Location, F.Food_Type, F.Meal_Type
FROM Food_Listings F
JOIN Providers P ON F.Provider_ID = P.Provider_ID
{where_sql}
ORDER BY F.Expiry_Date;
""", params)

st.dataframe(filtered, use_container_width=True)

# Quick chart: food items by Food_Type in filter
st.caption("Items by Food Type (current filters)")
chart_df = filtered.groupby("Food_Type")["Food_ID"].count().reset_index(name="Count")
st.bar_chart(chart_df, x="Food_Type", y="Count", use_container_width=True)

st.divider()

# ---------- CANNED QUERIES (Q1–Q13) ----------
st.header("Analysis & Reports (SQL)")

queries = {
"1. Providers & Receivers per City": """
SELECT P.City,
       COUNT(DISTINCT P.Provider_ID) AS Providers,
       COUNT(DISTINCT R.Receiver_ID) AS Receivers
FROM Providers P
LEFT JOIN Receivers R ON P.City = R.City
GROUP BY P.City
ORDER BY P.City;
""",
"2. Food contribution by Provider Type": """
SELECT Provider_Type, COUNT(Food_ID) AS Total_Food_Items
FROM Food_Listings
GROUP BY Provider_Type
ORDER BY Total_Food_Items DESC;
""",
"3. Contact info of Providers (select a city below)": """
SELECT Name, Type, City, Contact
FROM Providers
WHERE City = ?;
""",
"4. Receivers with most claims": """
SELECT R.Receiver_ID, R.Name AS Receiver_Name, COUNT(C.Claim_ID) AS Total_Claims
FROM Receivers R
JOIN Claims C ON R.Receiver_ID = C.Receiver_ID
GROUP BY R.Receiver_ID, R.Name
ORDER BY Total_Claims DESC
LIMIT 10;
""",
"5. Total quantity of food available": """
SELECT SUM(Quantity) AS Total_Food_Quantity
FROM Food_Listings;
""",
"6. City with highest number of food listings": """
SELECT P.City, COUNT(F.Food_ID) AS Total_Listings
FROM Food_Listings F
JOIN Providers P ON F.Provider_ID = P.Provider_ID
GROUP BY P.City
ORDER BY Total_Listings DESC
LIMIT 1;
""",
"7. Most common food types": """
SELECT Food_Type, COUNT(*) AS Count
FROM Food_Listings
GROUP BY Food_Type
ORDER BY Count DESC;
""",
"8. Claims per food item (with names)": """
SELECT F.Food_ID, F.Food_Name, COUNT(C.Claim_ID) AS Total_Claims
FROM Claims C
JOIN Food_Listings F ON C.Food_ID = F.Food_ID
GROUP BY F.Food_ID, F.Food_Name
ORDER BY Total_Claims DESC;
""",
"9. Provider with most completed claims": """
SELECT P.Provider_ID, P.Name AS Provider_Name, COUNT(*) AS Successful_Claims
FROM Claims C
JOIN Food_Listings F ON C.Food_ID = F.Food_ID
JOIN Providers P ON F.Provider_ID = P.Provider_ID
WHERE C.Status = 'Completed'
GROUP BY P.Provider_ID, P.Name
ORDER BY Successful_Claims DESC
LIMIT 1;
""",
"10. Claim status distribution (%)": """
SELECT Status,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM Claims), 2) AS Percentage
FROM Claims
GROUP BY Status
ORDER BY Percentage DESC;
""",
"11. Avg quantity per receiver (approx via listing qty)": """
SELECT R.Name AS Receiver_Name, ROUND(AVG(F.Quantity),2) AS Approx_Avg_Quantity
FROM Claims C
JOIN Receivers R ON C.Receiver_ID = R.Receiver_ID
JOIN Food_Listings F ON C.Food_ID = F.Food_ID
GROUP BY R.Name
ORDER BY Approx_Avg_Quantity DESC;
""",
"12. Most claimed meal type": """
SELECT F.Meal_Type, COUNT(*) AS Total_Claims
FROM Claims C
JOIN Food_Listings F ON C.Food_ID = F.Food_ID
GROUP BY F.Meal_Type
ORDER BY Total_Claims DESC;
""",
"13. Total quantity donated by each provider": """
SELECT P.Provider_ID, P.Name AS Provider_Name, SUM(F.Quantity) AS Total_Quantity
FROM Food_Listings F
JOIN Providers P ON F.Provider_ID = P.Provider_ID
GROUP BY P.Provider_ID, P.Name
ORDER BY Total_Quantity DESC;
"""
}

qname = st.selectbox("Pick a question:", list(queries.keys()))

extra_params = ()
if qname.startswith("3."):
    city_for_q3 = st.selectbox("City (for Q3)", cities)
    extra_params = (city_for_q3,)

df_q = run_query(queries[qname], extra_params)
st.dataframe(df_q, use_container_width=True)

# small chart suggestion for bar-like outputs
if "Count" in df_q.columns or "Total_Food_Items" in df_q.columns or "Total_Claims" in df_q.columns:
    try:
        st.bar_chart(df_q.set_index(df_q.columns[0]).iloc[:, -1])
    except Exception:
        pass

st.divider()

# ---------- CRUD ----------
st.header("Manage Data (CRUD)")

crud_tab1, crud_tab2, crud_tab3, crud_tab4 = st.tabs(["Add Provider", "Add Food Listing", "Update Food", "Delete Food"])

with crud_tab1:
    st.subheader("Add Provider")
    p_name = st.text_input("Name")
    p_type = st.selectbox("Type", provider_types or ["Restaurant","Grocery Store","Supermarket","Catering Service"])
    p_addr = st.text_area("Address")
    p_city = st.text_input("City")
    p_contact = st.text_input("Contact")
    if st.button("Add Provider"):
        if p_name and p_type and p_city:
            run_execute("""
                INSERT INTO Providers (Name, Type, Address, City, Contact)
                VALUES (?, ?, ?, ?, ?);
            """, (p_name, p_type, p_addr, p_city, p_contact))
            st.success("Provider added.")
        else:
            st.error("Name, Type, and City are required.")

with crud_tab2:
    st.subheader("Add Food Listing")
    # fetch providers for dropdown
    providers_df = run_query("SELECT Provider_ID, Name, Type FROM Providers ORDER BY Name;")
    prov_row = st.selectbox("Provider", providers_df.apply(lambda r: f"{r['Name']} (#{r['Provider_ID']}, {r['Type']})", axis=1))
    if not providers_df.empty:
        chosen_idx = st.session_state.get("prov_index", 0)
        provider_id = int(prov_row.split("#")[1].split(",")[0])
        provider_type = providers_df.loc[providers_df["Provider_ID"]==provider_id,"Type"].iloc[0]
    else:
        provider_id = None
        provider_type = ""

    f_name = st.text_input("Food Name")
    f_qty = st.number_input("Quantity", min_value=1, step=1)
    f_exp = st.date_input("Expiry Date", value=date.today())
    f_loc = st.text_input("Location (City)")
    f_food_type = st.selectbox("Food Type", food_types or ["Vegetarian","Non-Vegetarian","Vegan"])
    f_meal = st.selectbox("Meal Type", meal_types or ["Breakfast","Lunch","Dinner","Snacks"])

    if st.button("Add Food"):
        if provider_id and f_name and f_loc:
            run_execute("""
                INSERT INTO Food_Listings
                (Food_Name, Quantity, Expiry_Date, Provider_ID, Provider_Type, Location, Food_Type, Meal_Type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (f_name, int(f_qty), str(f_exp), provider_id, provider_type, f_loc, f_food_type, f_meal))
            st.success("Food listing added.")
        else:
            st.error("Provider, Food Name, and Location are required.")

with crud_tab3:
    st.subheader("Update Food Quantity")
    foods = run_query("SELECT Food_ID, Food_Name, Quantity FROM Food_Listings ORDER BY Food_ID;")
    if foods.empty:
        st.info("No food listings.")
    else:
        row = st.selectbox("Pick food to update", foods.apply(lambda r: f"#{r['Food_ID']} - {r['Food_Name']} (qty {r['Quantity']})", axis=1))
        food_id = int(row.split("#")[1].split(" ")[0])
        new_qty = st.number_input("New Quantity", min_value=0, step=1)
        if st.button("Update Quantity"):
            run_execute("UPDATE Food_Listings SET Quantity = ? WHERE Food_ID = ?;", (int(new_qty), food_id))
            st.success("Quantity updated.")

with crud_tab4:
    st.subheader("Delete Food Listing")
    foods2 = run_query("SELECT Food_ID, Food_Name FROM Food_Listings ORDER BY Food_ID;")
    if foods2.empty:
        st.info("No food listings.")
    else:
        row2 = st.selectbox("Pick food to delete", foods2.apply(lambda r: f"#{r['Food_ID']} - {r['Food_Name']}", axis=1))
        food_id2 = int(row2.split("#")[1].split(" ")[0])
        if st.button("Delete"):
            run_execute("DELETE FROM Food_Listings WHERE Food_ID = ?;", (food_id2,))
            st.success("Food listing deleted.")
