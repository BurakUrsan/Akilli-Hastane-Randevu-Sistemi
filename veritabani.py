import sqlite3
from werkzeug.security import generate_password_hash

VERITABANI_ADI = "hastane.db"

def baglanti_olustur():
    baglanti = sqlite3.connect(VERITABANI_ADI)
    baglanti.row_factory = sqlite3.Row

    baglanti.execute("PRAGMA foreign_keys = ON")

    return baglanti

def tablolari_olustur():
    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    imlec.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tc_no TEXT UNIQUE,
            ad TEXT NOT NULL,
            soyad TEXT NOT NULL,
            dogum_tarihi TEXT,
            email TEXT UNIQUE,
            telefon TEXT,
            sifre TEXT NOT NULL,
            rol TEXT NOT NULL,
            durum TEXT DEFAULT 'aktif'
        )
    """)

    imlec.execute("""
    CREATE TABLE IF NOT EXISTS doktorlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici_id INTEGER UNIQUE,
        doktor_adi TEXT NOT NULL,
        poliklinik TEXT NOT NULL,
        calisma_saatleri TEXT DEFAULT '09:00 - 17:00',
        durum TEXT DEFAULT 'aktif',
        FOREIGN KEY (kullanici_id) REFERENCES kullanicilar(id)
        )
    """)

    doktor_sutunlari = [
        satir["name"]
        for satir in imlec.execute(
            "PRAGMA table_info(doktorlar)"
        ).fetchall()
    ]

    if "calisma_saatleri" not in doktor_sutunlari:
        imlec.execute("""
            ALTER TABLE doktorlar
            ADD COLUMN calisma_saatleri TEXT DEFAULT '09:00 - 17:00'
        """)

    imlec.execute("""
        CREATE TABLE IF NOT EXISTS randevular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hasta_id INTEGER,
            doktor_id INTEGER,
            poliklinik TEXT NOT NULL,
            tarih TEXT NOT NULL,
            saat TEXT NOT NULL,
            durum TEXT DEFAULT 'aktif',
            hasta_notu TEXT,
            doktor_notu TEXT,
            olusturma_tarihi TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (hasta_id) REFERENCES kullanicilar(id),
            FOREIGN KEY (doktor_id) REFERENCES doktorlar(id)
        )
    """)

    imlec.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_tek_aktif_randevu
        ON randevular (
            doktor_id,
            tarih,
            saat
        )
        WHERE durum = 'aktif'
    """)

    imlec.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_hasta_ayni_saat_aktif
        ON randevular (
            hasta_id,
            tarih,
            saat
        )
        WHERE durum = 'aktif'
    """)

    imlec.execute("""
        CREATE TABLE IF NOT EXISTS bekleme_listesi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hasta_id INTEGER,
            doktor_id INTEGER,
            poliklinik TEXT NOT NULL,
            tarih TEXT NOT NULL,
            saat TEXT,
            durum TEXT DEFAULT 'beklemede',
            olusturma_tarihi TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (hasta_id) REFERENCES kullanicilar(id),
            FOREIGN KEY (doktor_id) REFERENCES doktorlar(id)
        )
    """)

    imlec.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_aktif_bekleme_kaydi
        ON bekleme_listesi (
            hasta_id,
            doktor_id,
            tarih,
            saat
        )
        WHERE durum = 'beklemede'
    """)

    imlec.execute("""
        CREATE TABLE IF NOT EXISTS bildirimler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici_id INTEGER,
            baslik TEXT NOT NULL,
            mesaj TEXT NOT NULL,
            bildirim_turu TEXT,
            durum TEXT DEFAULT 'gonderilmedi',
            olusturma_tarihi TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (kullanici_id) REFERENCES kullanicilar(id)
        )
    """)

    imlec.execute("""
        CREATE TABLE IF NOT EXISTS sifre_sifirlama (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            son_kullanma_tarihi TEXT NOT NULL,
            kullanildi INTEGER DEFAULT 0,
            olusturma_tarihi TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (kullanici_id) REFERENCES kullanicilar(id)
        )
    """)

    baglanti.commit()
    baglanti.close()

def mevcut_sifreleri_hashle():
    baglanti = baglanti_olustur()

    try:
        kullanicilar = baglanti.execute("""
            SELECT id, sifre
            FROM kullanicilar
        """).fetchall()

        for kullanici in kullanicilar:
            mevcut_sifre = kullanici["sifre"]

            if (
                mevcut_sifre.startswith("scrypt:")
                or mevcut_sifre.startswith("pbkdf2:")
            ):
                continue

            hashli_sifre = generate_password_hash(
                mevcut_sifre
            )

            baglanti.execute("""
                UPDATE kullanicilar
                SET sifre = ?
                WHERE id = ?
            """, (
                hashli_sifre,
                kullanici["id"]
            ))

        baglanti.commit()

    except Exception:
        baglanti.rollback()
        raise

    finally:
        baglanti.close()

def ornek_verileri_ekle():
    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    def kullanici_ekle(tc_no, ad, soyad, dogum_tarihi, email, telefon, sifre, rol, durum="aktif"):
        mevcut_kullanici = imlec.execute("""
            SELECT id FROM kullanicilar
            WHERE tc_no = ? OR email = ?
        """, (tc_no, email)).fetchone()

        if mevcut_kullanici:
            return mevcut_kullanici["id"]

        imlec.execute("""
            INSERT INTO kullanicilar
            (tc_no, ad, soyad, dogum_tarihi, email, telefon, sifre, rol, durum)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tc_no,
            ad,
            soyad,
            dogum_tarihi,
            email,
            telefon,
            generate_password_hash(sifre),
            rol,
            durum
        ))

        return imlec.lastrowid

    kullanici_ekle(
        "11111111111",
        "Hasta",
        "A",
        "2000-01-01",
        "hasta@example.com",
        "501 000 00 01",
        "Hasta123.",
        "hasta"
    )

    doktor_kullanici_id = kullanici_ekle(
        "22222222222",
        "Doktor",
        "A",
        "1985-01-01",
        "doktor@example.com",
        "501 000 00 02",
        "Doktor123.",
        "doktor"
    )

    kullanici_ekle(
        "33333333333",
        "Admin",
        "A",
        "1990-01-01",
        "admin@example.com",
        "501 000 00 03",
        "Admin123.",
        "yonetici"
    )

    mevcut_doktor = imlec.execute("""
        SELECT id FROM doktorlar
        WHERE kullanici_id = ?
    """, (doktor_kullanici_id,)).fetchone()

    if not mevcut_doktor:
        imlec.execute("""
            INSERT INTO doktorlar
            (kullanici_id, doktor_adi, poliklinik, durum)
            VALUES (?, ?, ?, ?)
        """, (
            doktor_kullanici_id,
            "Dr. A",
            "Dahiliye",
            "aktif"
        ))

    baglanti.commit()
    baglanti.close()

if __name__ == "__main__":
    tablolari_olustur()
    ornek_verileri_ekle()
    mevcut_sifreleri_hashle()

    print(
        "Veritabanı ve tablolar başarıyla oluşturuldu."
    )