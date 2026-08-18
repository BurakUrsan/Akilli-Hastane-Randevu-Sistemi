import sqlite3


baglanti = sqlite3.connect("hastane.db")
baglanti.row_factory = sqlite3.Row
imlec = baglanti.cursor()

print("TABLOLAR:")
tablolar = imlec.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table'
""").fetchall()

for tablo in tablolar:
    print("-", tablo["name"])

print("\nKULLANICILAR:")
kullanicilar = imlec.execute("""
    SELECT id, ad, soyad, email, rol, durum 
    FROM kullanicilar
""").fetchall()

for kullanici in kullanicilar:
    print(
        kullanici["id"],
        kullanici["ad"],
        kullanici["soyad"],
        kullanici["email"],
        kullanici["rol"],
        kullanici["durum"]
    )

print("\nDOKTORLAR:")
doktorlar = imlec.execute("""
    SELECT id, doktor_adi, poliklinik, durum 
    FROM doktorlar
""").fetchall()

for doktor in doktorlar:
    print(
        doktor["id"],
        doktor["doktor_adi"],
        doktor["poliklinik"],
        doktor["durum"]
    )

baglanti.close()