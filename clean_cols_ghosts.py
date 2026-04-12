"""
clean_cols_ghosts.py
--------------------
Removes all Coles entries that have no Image URL.
Also cleans up double 'Coles' in names.
"""

import sheets_helper

def cleanup():
    print("🚀 Starting Coles Visual Cleanup...")
    ws = sheets_helper.get_listings_worksheet()
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Sheet empty.")
        return

    header = rows[0]
    data = rows[1:]

    # 1: Name, 2: Store, 6: Image_URL
    NAME_IDX = 1
    STORE_IDX = 2
    IMAGE_IDX = 6

    final_rows = [header]
    removed_count = 0

    for r in data:
        store = r[STORE_IDX].strip()
        image = r[IMAGE_IDX].strip()
        name  = r[NAME_IDX].strip()
        
        # Cleanup double Coles bug
        if name.startswith("Coles Coles "):
            name = name.replace("Coles Coles ", "Coles ", 1)
            r[NAME_IDX] = name

        if store == "Coles" and not image:
            removed_count += 1
            continue
            
        final_rows.append(r)

    print(f"Removed {removed_count} Coles 'ghost' entries.")
    
    if removed_count > 0:
        ws.clear()
        ws.update('A1', final_rows)
        print("DONE.")
    else:
        print("No ghosts found.")

if __name__ == "__main__":
    cleanup()
