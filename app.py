from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import random
import re
import sqlite3
import os
import smtplib
import ssl
import secrets
import hashlib
from dotenv import load_dotenv
from email.message import EmailMessage
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    ""
).strip()

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY ayarlanmamış."
    )

from veritabani import (
    baglanti_olustur,
    tablolari_olustur,
    ornek_verileri_ekle,
    mevcut_sifreleri_hashle
)

tablolari_olustur()
ornek_verileri_ekle()
mevcut_sifreleri_hashle()

def guvenlik_kodu_uret():
    session["guvenlik_kodu"] = str(random.randint(10000, 99999))


def sifre_kurallarina_uygun_mu(sifre):
    en_az_8 = len(sifre) >= 8
    buyuk_harf = re.search(r"[A-ZÇĞİÖŞÜ]", sifre) is not None
    kucuk_harf = re.search(r"[a-zçğıöşü]", sifre) is not None
    rakam = re.search(r"[0-9]", sifre) is not None
    sembol = re.search(r"[^A-Za-zÇĞİÖŞÜçğıöşü0-9]", sifre) is not None

    return en_az_8 and buyuk_harf and kucuk_harf and rakam and sembol

def sifre_sifirlama_token_hash_olustur(token):
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

def sifre_sifirlama_kaydi_olustur(kullanici_id):
    token = secrets.token_urlsafe(32)

    token_hash = sifre_sifirlama_token_hash_olustur(
        token
    )

    son_kullanma_tarihi = (
        datetime.now() + timedelta(minutes=30)
    ).strftime("%Y-%m-%d %H:%M:%S")

    baglanti = baglanti_olustur()

    try:
        imlec = baglanti.cursor()

        imlec.execute("""
            UPDATE sifre_sifirlama
            SET kullanildi = 1
            WHERE kullanici_id = ?
              AND kullanildi = 0
        """, (kullanici_id,))

        imlec.execute("""
            INSERT INTO sifre_sifirlama (
                kullanici_id,
                token_hash,
                son_kullanma_tarihi,
                kullanildi
            )
            VALUES (?, ?, ?, 0)
        """, (
            kullanici_id,
            token_hash,
            son_kullanma_tarihi
        ))

        baglanti.commit()

        return token

    except Exception:
        baglanti.rollback()
        raise

    finally:
        baglanti.close()

def telefon_formatla(telefon):
    rakamlar = re.sub(r"\D", "", telefon)

    if len(rakamlar) == 10:
        return f"{rakamlar[0:3]} {rakamlar[3:6]} {rakamlar[6:8]} {rakamlar[8:10]}"

    if len(rakamlar) == 11:
        return f"{rakamlar[0:4]} {rakamlar[4:7]} {rakamlar[7:9]} {rakamlar[9:11]}"

    return telefon

def email_gecerli_mi(email):
    return re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        email
    ) is not None


def dogum_tarihi_gecerli_mi(dogum_tarihi):
    try:
        tarih = datetime.strptime(
            dogum_tarihi,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return False

    return tarih <= date.today()

def kullanici_bul(kullanici_girisi):
    kullanici_girisi = kullanici_girisi.strip().lower()

    baglanti = baglanti_olustur()
    kullanici_satiri = baglanti.execute("""
        SELECT *
        FROM kullanicilar
        WHERE LOWER(tc_no) = ? OR LOWER(email) = ?
    """, (kullanici_girisi, kullanici_girisi)).fetchone()
    baglanti.close()

    if kullanici_satiri:
        kullanici = {
            "id": kullanici_satiri["id"],
            "tc_no": kullanici_satiri["tc_no"],
            "sifre": kullanici_satiri["sifre"],
            "rol": kullanici_satiri["rol"],
            "ad": kullanici_satiri["ad"],
            "soyad": kullanici_satiri["soyad"],
            "email": kullanici_satiri["email"],
            "telefon": kullanici_satiri["telefon"] or "",
            "dogum_tarihi": kullanici_satiri["dogum_tarihi"] or "",
            "durum": "Aktif" if kullanici_satiri["durum"] == "aktif" else kullanici_satiri["durum"]
        }

        if kullanici["rol"] == "doktor":
            baglanti = baglanti_olustur()
            doktor_satiri = baglanti.execute("""
                SELECT
                doktor_adi,
                poliklinik,
                calisma_saatleri,
                durum
            FROM doktorlar
            WHERE kullanici_id = ?
            """, (kullanici["id"],)).fetchone()
            baglanti.close()

            if doktor_satiri:
                kullanici["doktor_adi"] = doktor_satiri["doktor_adi"]
                kullanici["brans"] = doktor_satiri["poliklinik"]

                kullanici["calisma_saatleri"] = (
                    doktor_satiri["calisma_saatleri"]
                    or "09:00 - 17:00"
                )

                kullanici["durum"] = (
                    "Aktif"
                    if doktor_satiri["durum"] == "aktif"
                    else "Pasif"
                )

        kullanici_anahtar = kullanici["tc_no"] if kullanici["tc_no"] else kullanici["email"]

        return kullanici_anahtar, kullanici

    return None, None


def kullanici_var_mi(tc, email):
    _, tc_kullanicisi = kullanici_bul(tc)
    _, email_kullanicisi = kullanici_bul(email)

    return tc_kullanicisi is not None or email_kullanicisi is not None

def sqlite_hasta_kaydet(tc, ad, soyad, dogum_tarihi, email, telefon, sifre):
    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    imlec.execute("""
        INSERT INTO kullanicilar
        (tc_no, ad, soyad, dogum_tarihi, email, telefon, sifre, rol, durum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tc,
        ad,
        soyad,
        dogum_tarihi,
        email,
        telefon,
        generate_password_hash(sifre),
        "hasta",
        "aktif"
    ))

    yeni_kullanici_id = imlec.lastrowid

    baglanti.commit()
    baglanti.close()

    return yeni_kullanici_id

def email_baska_kullanicida_mi(email, mevcut_kullanici_id):
    email = email.strip().lower()

    baglanti = baglanti_olustur()

    try:
        kullanici = baglanti.execute("""
            SELECT id
            FROM kullanicilar
            WHERE LOWER(email) = LOWER(?)
              AND id != ?
            LIMIT 1
        """, (
            email,
            mevcut_kullanici_id
        )).fetchone()

        return kullanici is not None

    finally:
        baglanti.close()

def kullanici_giris_yapabilir_mi(kullanici_id, rol):
    baglanti = baglanti_olustur()

    try:
        if rol == "doktor":
            durum = baglanti.execute("""
                SELECT
                    k.durum AS kullanici_durumu,
                    d.durum AS doktor_durumu
                FROM kullanicilar k
                LEFT JOIN doktorlar d
                    ON d.kullanici_id = k.id
                WHERE k.id = ?
                  AND k.rol = 'doktor'
            """, (kullanici_id,)).fetchone()

            if not durum:
                return False

            return (
                durum["kullanici_durumu"] == "aktif"
                and durum["doktor_durumu"] == "aktif"
            )

        durum = baglanti.execute("""
            SELECT durum
            FROM kullanicilar
            WHERE id = ?
        """, (kullanici_id,)).fetchone()

        return (
            durum is not None
            and durum["durum"] == "aktif"
        )

    finally:
        baglanti.close()

def giris_kontrol(istenen_rol=None):
    if "rol" not in session:
        return False

    if istenen_rol and session["rol"] != istenen_rol:
        return False

    return True


def tarih_goster(tarih_iso):
    try:
        return datetime.strptime(tarih_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return tarih_iso

def eposta_gonder(alici_email, konu, mesaj):
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = os.getenv("SMTP_PORT", "465").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()
    smtp_security = os.getenv(
        "SMTP_SECURITY",
        "ssl"
    ).strip().lower()

    if smtp_security not in ("ssl", "starttls"):
        raise RuntimeError(
            "SMTP_SECURITY yalnızca "
            "'ssl' veya 'starttls' olabilir."
        )

    if not smtp_host:
        raise RuntimeError(
            "SMTP_HOST ayarlanmamış."
        )

    if not smtp_from:
        raise RuntimeError(
            "SMTP_FROM ayarlanmamış."
        )

    try:
        smtp_port = int(smtp_port)
    except ValueError:
        raise RuntimeError(
            "SMTP_PORT geçerli bir sayı olmalıdır."
        )

    if smtp_user and not smtp_password:
        raise RuntimeError(
            "SMTP_PASSWORD ayarlanmamış."
        )

    eposta = EmailMessage()

    eposta["Subject"] = konu
    eposta["From"] = smtp_from
    eposta["To"] = alici_email

    eposta.set_content(mesaj)

    ssl_context = ssl.create_default_context()

    if smtp_security == "ssl":

        with smtplib.SMTP_SSL(
            smtp_host,
            smtp_port,
            context=ssl_context,
            timeout=20
        ) as sunucu:

            if smtp_user:
                sunucu.login(
                    smtp_user,
                    smtp_password
                )

            sunucu.send_message(eposta)

    elif smtp_security == "starttls":

        with smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20
        ) as sunucu:

            sunucu.ehlo()

            sunucu.starttls(
                context=ssl_context
            )

            sunucu.ehlo()

            if smtp_user:
                sunucu.login(
                    smtp_user,
                    smtp_password
                )

            sunucu.send_message(eposta)


def bildirim_kaydi_olustur(
    kullanici_id,
    baslik,
    mesaj
):
    baglanti = baglanti_olustur()

    try:
        imlec = baglanti.cursor()

        imlec.execute("""
            INSERT INTO bildirimler
            (
                kullanici_id,
                baslik,
                mesaj,
                bildirim_turu,
                durum
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            kullanici_id,
            baslik,
            mesaj,
            "eposta",
            "gonderilmedi"
        ))

        bildirim_id = imlec.lastrowid

        baglanti.commit()

        return bildirim_id

    finally:
        baglanti.close()


def bildirim_durum_guncelle(
    bildirim_id,
    yeni_durum
):
    baglanti = baglanti_olustur()

    try:
        baglanti.execute("""
            UPDATE bildirimler
            SET durum = ?
            WHERE id = ?
        """, (
            yeni_durum,
            bildirim_id
        ))

        baglanti.commit()

    finally:
        baglanti.close()


def bosalan_randevu_bildirimlerini_gonder(
    doktor_id,
    poliklinik,
    tarih,
    saat
):
    baglanti = baglanti_olustur()

    try:
        bekleyenler = baglanti.execute("""
            SELECT DISTINCT
                b.hasta_id,
                k.ad,
                k.soyad,
                k.email,
                d.doktor_adi

            FROM bekleme_listesi b

            JOIN kullanicilar k
                ON b.hasta_id = k.id

            JOIN doktorlar d
                ON b.doktor_id = d.id

            WHERE b.doktor_id = ?
              AND b.tarih = ?
              AND b.saat = ?
              AND b.durum = 'beklemede'
              AND k.durum = 'aktif'
              AND k.email IS NOT NULL
              AND TRIM(k.email) != ''

            ORDER BY b.olusturma_tarihi ASC
        """, (
            doktor_id,
            tarih,
            saat
        )).fetchall()

    finally:
        baglanti.close()

    gonderilen_sayisi = 0
    basarisiz_sayisi = 0

    for hasta in bekleyenler:

        baslik = (
            "Beklediğiniz randevu saati boşaldı"
        )

        mesaj = f"""Merhaba {hasta['ad']} {hasta['soyad']},

Bekleme listesinde bulunduğunuz randevu saati boşalmıştır.

Poliklinik: {poliklinik}
Doktor: {hasta['doktor_adi']}
Tarih: {tarih_goster(tarih)}
Saat: {saat}

Bu bildirim aynı randevu saati için bekleme listesinde bulunan diğer hastalara da gönderilmiştir.

Bu e-posta sizin için otomatik olarak randevu oluşturmaz. Randevuyu sistem üzerinden ilk tamamlayan hasta alacaktır.

Akıllı Hastane Randevu Sistemi
"""

        try:
            bildirim_id = bildirim_kaydi_olustur(
                hasta["hasta_id"],
                baslik,
                mesaj
            )

            try:
                eposta_gonder(
                    hasta["email"],
                    baslik,
                    mesaj
                )

                bildirim_durum_guncelle(
                    bildirim_id,
                    "gonderildi"
                )

                gonderilen_sayisi += 1

            except Exception:
                bildirim_durum_guncelle(
                    bildirim_id,
                    "basarisiz"
                )

                basarisiz_sayisi += 1

                app.logger.exception(
                    "E-posta gönderimi başarısız oldu. "
                    "Hasta ID: %s",
                    hasta["hasta_id"]
                )

        except Exception:
            basarisiz_sayisi += 1

            app.logger.exception(
                "Bildirim kaydı oluşturulamadı. "
                "Hasta ID: %s",
                hasta["hasta_id"]
            )

    return {
        "bekleyen": len(bekleyenler),
        "gonderilen": gonderilen_sayisi,
        "basarisiz": basarisiz_sayisi
    }

def aktif_kullanici_id_getir():
    kullanici_id = session.get("kullanici_id")

    if kullanici_id:
        return kullanici_id

    # Eski açık session varsa geriye dönük destek
    kullanici_anahtar = session.get("kullanici_anahtar")

    if not kullanici_anahtar:
        return None

    baglanti = baglanti_olustur()

    try:
        kullanici = baglanti.execute("""
            SELECT id
            FROM kullanicilar
            WHERE tc_no = ?
               OR LOWER(email) = LOWER(?)
            LIMIT 1
        """, (
            kullanici_anahtar,
            kullanici_anahtar
        )).fetchone()

        if not kullanici:
            return None

        session["kullanici_id"] = kullanici["id"]

        return kullanici["id"]

    finally:
        baglanti.close()


def kullanici_bilgilerini_id_ile_getir(kullanici_id):
    if not kullanici_id:
        return None

    baglanti = baglanti_olustur()

    try:
        kullanici = baglanti.execute("""
            SELECT
                id,
                tc_no,
                ad,
                soyad,
                dogum_tarihi,
                email,
                telefon,
                sifre,
                rol,
                durum
            FROM kullanicilar
            WHERE id = ?
        """, (kullanici_id,)).fetchone()

        if not kullanici:
            return None

        return {
            "id": kullanici["id"],
            "tc_no": kullanici["tc_no"],
            "ad": kullanici["ad"],
            "soyad": kullanici["soyad"],
            "dogum_tarihi": kullanici["dogum_tarihi"] or "",
            "email": kullanici["email"] or "",
            "telefon": kullanici["telefon"] or "",
            "sifre": kullanici["sifre"],
            "rol": kullanici["rol"],
            "durum": (
                "Aktif"
                if kullanici["durum"] == "aktif"
                else "Pasif"
            )
        }

    finally:
        baglanti.close()


def oturum_bilgilerini_yenile(kullanici_id):
    kullanici = kullanici_bilgilerini_id_ile_getir(
        kullanici_id
    )

    if not kullanici:
        return False

    kullanici_anahtar = (
        kullanici["tc_no"]
        if kullanici["tc_no"]
        else kullanici["email"]
    )

    session["kullanici_id"] = kullanici["id"]
    session["kullanici_anahtar"] = kullanici_anahtar
    session["ad"] = kullanici["ad"]
    session["soyad"] = kullanici["soyad"]
    session["rol"] = kullanici["rol"]

    return True

def aktif_hasta_id_getir():
    kullanici_id = aktif_kullanici_id_getir()

    if not kullanici_id:
        return None

    baglanti = baglanti_olustur()

    try:
        hasta = baglanti.execute("""
            SELECT id
            FROM kullanicilar
            WHERE id = ?
              AND rol = 'hasta'
              AND durum = 'aktif'
        """, (kullanici_id,)).fetchone()

        if hasta:
            return hasta["id"]

        return None

    finally:
        baglanti.close()

def sqlite_randevu_satirini_sozluge_cevir(randevu):
    durum = "Aktif"

    if randevu["durum"] == "iptal_edildi":
        durum = "İptal Edildi"

    return {
        "id": randevu["id"],
        "hasta_anahtar": session.get("kullanici_anahtar"),
        "hasta_ad_soyad": f"{randevu['hasta_ad']} {randevu['hasta_soyad']}",
        "poliklinik": randevu["poliklinik"],
        "doktor": randevu["doktor_adi"],
        "tarih": randevu["tarih"],
        "tarih_goster": tarih_goster(randevu["tarih"]),
        "saat": randevu["saat"],
        "hasta_notu": randevu["hasta_notu"] or "",
        "doktor_notu": randevu["doktor_notu"] or "",
        "durum": durum
    }


def hasta_randevularini_getir():
    hasta_id = aktif_hasta_id_getir()

    if not hasta_id:
        return []

    baglanti = baglanti_olustur()
    randevu_satirlari = baglanti.execute("""
        SELECT 
            r.id,
            r.poliklinik,
            r.tarih,
            r.saat,
            r.durum,
            r.hasta_notu,
            r.doktor_notu,
            k.ad AS hasta_ad,
            k.soyad AS hasta_soyad,
            d.doktor_adi
        FROM randevular r
        JOIN kullanicilar k ON r.hasta_id = k.id
        JOIN doktorlar d ON r.doktor_id = d.id
        WHERE r.hasta_id = ?
        ORDER BY r.tarih ASC, r.saat ASC
    """, (hasta_id,)).fetchall()
    baglanti.close()

    return [
        sqlite_randevu_satirini_sozluge_cevir(randevu)
        for randevu in randevu_satirlari
    ]


def hasta_aktif_randevularini_getir():
    return [
        randevu for randevu in hasta_randevularini_getir()
        if randevu["durum"] == "Aktif"
    ]


def hasta_iptal_randevularini_getir():
    return [
        randevu for randevu in hasta_randevularini_getir()
        if randevu["durum"] == "İptal Edildi"
    ]

def hasta_bekleme_kayitlarini_getir():
    hasta_id = aktif_hasta_id_getir()

    if not hasta_id:
        return []

    baglanti = baglanti_olustur()

    kayit_satirlari = baglanti.execute("""
        SELECT
            b.id,
            b.poliklinik,
            b.tarih,
            b.saat,
            b.durum,
            b.olusturma_tarihi,
            d.doktor_adi
        FROM bekleme_listesi b
        JOIN doktorlar d
            ON b.doktor_id = d.id
        WHERE b.hasta_id = ?
        ORDER BY
            b.olusturma_tarihi DESC,
            b.id DESC
    """, (hasta_id,)).fetchall()

    baglanti.close()

    bekleme_kayitlari = []

    for kayit in kayit_satirlari:

        if kayit["durum"] == "beklemede":
            durum_goster = "Aktif"

        elif kayit["durum"] == "randevu_alindi":
            durum_goster = "Randevu Alındı"

        else:
            durum_goster = "Listeden Çıkıldı"

        bekleme_kayitlari.append({
            "id": kayit["id"],
            "poliklinik": kayit["poliklinik"],
            "doktor": kayit["doktor_adi"],
            "tarih": kayit["tarih"],
            "tarih_goster": tarih_goster(
                kayit["tarih"]
            ),
            "saat": kayit["saat"],
            "durum": durum_goster
        })

    return bekleme_kayitlari

def calisma_saatleri_ayristir(calisma_saatleri):
    if not calisma_saatleri:
        return None

    eslesme = re.fullmatch(
        r"\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*",
        calisma_saatleri
    )

    if not eslesme:
        return None

    try:
        baslangic = datetime.strptime(
            eslesme.group(1),
            "%H:%M"
        ).time()

        bitis = datetime.strptime(
            eslesme.group(2),
            "%H:%M"
        ).time()

    except ValueError:
        return None

    if baslangic >= bitis:
        return None

    return baslangic, bitis


def calisma_saatleri_gecerli_mi(calisma_saatleri):
    return (
        calisma_saatleri_ayristir(
            calisma_saatleri
        ) is not None
    )


def doktor_calisma_saatleri_getir(doktor_adi):
    baglanti = baglanti_olustur()

    try:
        doktor = baglanti.execute("""
            SELECT calisma_saatleri
            FROM doktorlar
            WHERE doktor_adi = ?
        """, (doktor_adi,)).fetchone()

    finally:
        baglanti.close()

    if not doktor:
        return None

    return doktor["calisma_saatleri"]

def doktor_uygun_randevu_saatleri_getir(doktor_adi):
    calisma_saatleri = doktor_calisma_saatleri_getir(
        doktor_adi
    )

    aralik = calisma_saatleri_ayristir(
        calisma_saatleri
    )

    if not aralik:
        return []

    baslangic, bitis = aralik

    bugun = date.today()

    mevcut_saat = datetime.combine(
        bugun,
        baslangic
    )

    bitis_zamani = datetime.combine(
        bugun,
        bitis
    )

    uygun_saatler = []

    while mevcut_saat <= bitis_zamani:
        uygun_saatler.append(
            mevcut_saat.strftime("%H:%M")
        )

        mevcut_saat += timedelta(hours=1)

    return uygun_saatler

def doktor_calisma_saatinde_mi(doktor_adi, saat):
    return saat in doktor_uygun_randevu_saatleri_getir(
        doktor_adi
    )

def randevu_zamani_dogrula(tarih, saat):

    try:
        randevu_zamani = datetime.strptime(
            f"{tarih} {saat}",
            "%Y-%m-%d %H:%M"
        )

    except ValueError:
        return (
            False,
            "Geçerli bir randevu tarihi ve saati seçiniz."
        )

    if randevu_zamani <= datetime.now():
        return (
            False,
            "Geçmiş bir tarih veya saat seçemezsiniz."
        )

    return True, None

def randevu_saati_dolu_mu(doktor, tarih, saat):
    doktor_id = sqlite_doktor_id_getir(doktor)

    if not doktor_id:
        return False

    baglanti = baglanti_olustur()
    randevu = baglanti.execute("""
        SELECT id
        FROM randevular
        WHERE doktor_id = ?
          AND tarih = ?
          AND saat = ?
          AND durum = ?
    """, (
        doktor_id,
        tarih,
        saat,
        "aktif"
    )).fetchone()
    baglanti.close()

    if randevu:
        return True

    return False

def hastanin_aktif_randevusu_var_mi(doktor, tarih, saat):
    hasta_id = aktif_hasta_id_getir()

    if not hasta_id:
        return False

    return hasta_ayni_saatte_aktif_randevusu_var_mi(
        hasta_id,
        tarih,
        saat
    )

def bekleme_kaydi_var_mi(doktor, tarih, saat):
    hasta_id = aktif_hasta_id_getir()
    doktor_id = sqlite_doktor_id_getir(doktor)

    if not hasta_id or not doktor_id:
        return False

    baglanti = baglanti_olustur()

    kayit = baglanti.execute("""
        SELECT id
        FROM bekleme_listesi
        WHERE hasta_id = ?
          AND doktor_id = ?
          AND tarih = ?
          AND saat = ?
          AND durum = ?
        LIMIT 1
    """, (
        hasta_id,
        doktor_id,
        tarih,
        saat,
        "beklemede"
    )).fetchone()

    baglanti.close()

    return kayit is not None

def doktor_bilgilerini_getir():
    kullanici_id = aktif_kullanici_id_getir()

    if not kullanici_id:
        return None

    baglanti = baglanti_olustur()

    try:
        doktor = baglanti.execute("""
            SELECT
                d.id AS doktor_id,
                d.doktor_adi,
                d.poliklinik,
                d.calisma_saatleri,

                k.id AS kullanici_id,
                k.email,
                k.telefon

            FROM doktorlar d

            JOIN kullanicilar k
                ON d.kullanici_id = k.id

            WHERE k.id = ?
              AND k.rol = 'doktor'
        """, (
            kullanici_id,
        )).fetchone()

        if not doktor:
            return None

        return {
            "doktor_id": doktor["doktor_id"],
            "kullanici_id": doktor["kullanici_id"],
            "doktor_adi": doktor["doktor_adi"],
            "brans": doktor["poliklinik"],
            "email": doktor["email"] or "",
            "telefon": (
                doktor["telefon"]
                or "Belirtilmedi"
            ),
            "telefon_form": (
                doktor["telefon"]
                or ""
            ),
            "calisma_saatleri": (
                doktor["calisma_saatleri"]
                or "09:00 - 17:00"
            )
        }

    finally:
        baglanti.close()

def aktif_doktor_id_getir():
    kullanici_id = aktif_kullanici_id_getir()

    if not kullanici_id:
        return None

    baglanti = baglanti_olustur()

    try:
        doktor = baglanti.execute("""
            SELECT d.id
            FROM doktorlar d

            JOIN kullanicilar k
                ON d.kullanici_id = k.id

            WHERE d.kullanici_id = ?
              AND d.durum = 'aktif'
              AND k.durum = 'aktif'
        """, (
            kullanici_id,
        )).fetchone()

        if doktor:
            return doktor["id"]

        return None

    finally:
        baglanti.close()

def doktor_randevu_durumunu_goster(durum):
    if durum == "iptal_edildi":
        return "İptal Edildi"

    return "Aktif"

#05.08
def doktor_randevularini_getir(doktor_adi=None):
    doktor_id = aktif_doktor_id_getir()

    if not doktor_id:
        return []

    baglanti = baglanti_olustur()
    randevu_satirlari = baglanti.execute("""
        SELECT
            r.id,
            r.poliklinik,
            r.tarih,
            r.saat,
            r.durum,
            r.hasta_notu,
            r.doktor_notu,
            h.ad AS hasta_ad,
            h.soyad AS hasta_soyad,
            h.telefon AS hasta_telefon,
            h.email AS hasta_email,
            d.doktor_adi
        FROM randevular r
        JOIN kullanicilar h ON r.hasta_id = h.id
        JOIN doktorlar d ON r.doktor_id = d.id
        WHERE r.doktor_id = ?
        ORDER BY r.tarih ASC, r.saat ASC
    """, (doktor_id,)).fetchall()
    baglanti.close()

    doktora_ait_randevular = []

    for index, randevu in enumerate(randevu_satirlari, start=1):
        doktora_ait_randevular.append({
            "id": randevu["id"],
            "hasta_sira_kodu": index,
            "hasta_ad_soyad": f"{randevu['hasta_ad']} {randevu['hasta_soyad']}",
            "hasta_detay_ad_soyad": f"{randevu['hasta_ad']} {randevu['hasta_soyad']}",
            "hasta_telefon": randevu["hasta_telefon"] or "Belirtilmedi",
            "hasta_email": randevu["hasta_email"] or "Belirtilmedi",
            "poliklinik": randevu["poliklinik"],
            "doktor": randevu["doktor_adi"],
            "tarih": randevu["tarih"],
            "tarih_goster": tarih_goster(randevu["tarih"]),
            "saat": randevu["saat"],
            "hasta_notu": randevu["hasta_notu"] or "",
            "doktor_notu": randevu["doktor_notu"] or "",
            "durum": doktor_randevu_durumunu_goster(randevu["durum"])
        })

    return doktora_ait_randevular
#05.08
def sqlite_doktor_notu_guncelle(randevu_id, doktor_notu):
    doktor_id = aktif_doktor_id_getir()

    if not doktor_id:
        return False

    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    imlec.execute("""
        UPDATE randevular
        SET doktor_notu = ?
        WHERE id = ? AND doktor_id = ?
    """, (
        doktor_notu,
        randevu_id,
        doktor_id
    ))

    basarili = imlec.rowcount > 0

    baglanti.commit()
    baglanti.close()

    return basarili

@app.route("/")
def ana_sayfa():
    return redirect(url_for("giris"))

@app.route("/giris", methods=["GET", "POST"])
def giris():
    hata = None

    if "guvenlik_kodu" not in session:
        guvenlik_kodu_uret()

    if request.method == "POST":
        kullanici_girisi = request.form.get(
            "kullanici_girisi",
            ""
        ).strip()

        sifre = request.form.get(
            "sifre",
            ""
        ).strip()

        girilen_kod = request.form.get(
            "guvenlik_kodu",
            ""
        ).strip()

        if girilen_kod != session.get("guvenlik_kodu"):
            hata = "Güvenlik kodu hatalı."
            guvenlik_kodu_uret()

            return render_template(
                "giris.html",
                hata=hata,
                guvenlik_kodu=session["guvenlik_kodu"]
            )

        kullanici_anahtar, kullanici = kullanici_bul(
            kullanici_girisi
        )

        if (
        kullanici
        and check_password_hash(
            kullanici["sifre"],
            sifre
        )
    ):
        
            if not kullanici_giris_yapabilir_mi(
                kullanici["id"],
                kullanici["rol"]
            ):
                hata = (
                    "Hesabınız pasif durumdadır. "
                    "Sisteme giriş yapamazsınız."
                )

                guvenlik_kodu_uret()

            else:
                session["kullanici_anahtar"] = kullanici_anahtar
                session["kullanici_id"] = kullanici["id"]
                session["ad"] = kullanici["ad"]
                session["soyad"] = kullanici["soyad"]
                session["rol"] = kullanici["rol"]

                guvenlik_kodu_uret()

                if kullanici["rol"] == "hasta":
                    return redirect(
                        url_for("hasta_panel")
                    )

                elif kullanici["rol"] == "doktor":
                    return redirect(
                        url_for("doktor_panel")
                    )

                elif kullanici["rol"] == "yonetici":
                    return redirect(
                        url_for("admin_panel")
                    )

        else:
            hata = (
                "TC kimlik numarası/e-posta "
                "veya şifre hatalı."
            )

            guvenlik_kodu_uret()

    return render_template(
        "giris.html",
        hata=hata,
        guvenlik_kodu=session["guvenlik_kodu"]
    )

@app.route("/kayit", methods=["GET", "POST"])
def kayit():
    hata = None
    basari = None

    form_data = {
        "tc": "",
        "ad": "",
        "soyad": "",
        "dogum_tarihi": "",
        "email": "",
        "telefon": "",
        "sifre": "",
        "kvkk_onay": False,
        "uyelik_onay": False
    }

    if request.method == "POST":
        telefon_girisi = request.form.get("telefon", "").strip()
        telefon_rakamlar = re.sub(r"\D", "", telefon_girisi)

        form_data = {
            "tc": request.form.get("tc", "").strip(),
            "ad": request.form.get("ad", "").strip(),
            "soyad": request.form.get("soyad", "").strip(),
            "dogum_tarihi": request.form.get("dogum_tarihi", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "telefon": telefon_formatla(telefon_rakamlar),
            "sifre": request.form.get("sifre", "").strip(),
            "kvkk_onay": request.form.get("kvkk_onay") == "on",
            "uyelik_onay": request.form.get("uyelik_onay") == "on"
        }

        tc = form_data["tc"]
        ad = form_data["ad"]
        soyad = form_data["soyad"]
        dogum_tarihi = form_data["dogum_tarihi"]
        email = form_data["email"]
        telefon = form_data["telefon"]
        sifre = form_data["sifre"]
        kvkk_onay = form_data["kvkk_onay"]
        uyelik_onay = form_data["uyelik_onay"]

        if not tc or not ad or not soyad or not dogum_tarihi or not email or not telefon or not sifre:
            hata = "Lütfen tüm alanları doldurunuz."

        elif not tc.isdigit() or len(tc) != 11:
            hata = "TC kimlik numarası 11 haneli olmalıdır."

        elif not dogum_tarihi_gecerli_mi(dogum_tarihi):
            hata = (
                "Geçerli ve gelecekte olmayan "
                "bir doğum tarihi giriniz."
        )

        elif not email_gecerli_mi(email):
            hata = "Geçerli bir e-posta adresi giriniz."

        elif len(telefon_rakamlar) not in [10, 11]:
            hata = "Telefon numarası 10 veya 11 haneli olmalıdır."

        elif not sifre_kurallarina_uygun_mu(sifre):
            hata = "Şifre en az 8 karakter olmalı; büyük harf, küçük harf, rakam ve sembol içermelidir."

        elif not kvkk_onay or not uyelik_onay:
            hata = "KVKK onayı ve kullanım şartları kabul edilmelidir."

        elif kullanici_var_mi(tc, email):
            hata = "Bu TC kimlik numarası veya e-posta ile kayıtlı kullanıcı zaten var."

        else:
            try:
                sqlite_hasta_kaydet(
                    tc,
                    ad,
                    soyad,
                    dogum_tarihi,
                    email,
                    telefon,
                    sifre
                )

                basari = "Kayıt başarılı. Giriş ekranından hesabınıza giriş yapabilirsiniz."

                form_data = {
                    "tc": "",
                    "ad": "",
                    "soyad": "",
                    "dogum_tarihi": "",
                    "email": "",
                    "telefon": "",
                    "sifre": "",
                    "kvkk_onay": False,
                    "uyelik_onay": False
                }

            except Exception:
                hata = "Kayıt sırasında bir hata oluştu. Lütfen bilgileri kontrol edip tekrar deneyiniz."

    return render_template(
        "kayit.html",
        hata=hata,
        basari=basari,
        form_data=form_data
    )

@app.route("/sifremi-unuttum", methods=["GET", "POST"])
def sifremi_unuttum():
    hata = None
    basari = None

    form_data = {
        "email": ""
    }

    if request.method == "POST":
        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        form_data["email"] = email

        if not email:
            hata = "Lütfen e-posta adresinizi giriniz."

        else:
            baglanti = baglanti_olustur()

            try:
                kullanici = baglanti.execute("""
                    SELECT
                        id,
                        ad,
                        soyad,
                        email
                    FROM kullanicilar
                    WHERE LOWER(email) = ?
                      AND durum = 'aktif'
                """, (email,)).fetchone()

            finally:
                baglanti.close()

            if kullanici:
                try:
                    token = sifre_sifirlama_kaydi_olustur(
                        kullanici["id"]
                    )

                    sifirlama_linki = (
                        request.host_url.rstrip("/")
                        + "/sifre-sifirla/"
                        + token
                    )

                    konu = "Akıllı Hastane - Şifre Sıfırlama"

                    mesaj = f"""Merhaba {kullanici['ad']} {kullanici['soyad']},

Akıllı Hastane Randevu Sistemi hesabınız için şifre sıfırlama talebi alınmıştır.

Yeni şifrenizi oluşturmak için aşağıdaki bağlantıyı kullanabilirsiniz:

{sifirlama_linki}

Bu bağlantı 30 dakika boyunca geçerlidir ve yalnızca bir kez kullanılabilir.

Eğer bu işlemi siz talep etmediyseniz bu e-postayı dikkate almayınız.

Akıllı Hastane Randevu Sistemi
"""

                    eposta_gonder(
                        kullanici["email"],
                        konu,
                        mesaj
                    )

                except Exception:
                    app.logger.exception(
                        "Şifre sıfırlama e-postası gönderilemedi."
                    )

            basari = (
                "E-posta adresiniz sistemde kayıtlıysa "
                "şifre sıfırlama bağlantısı gönderilmiştir."
            )

    return render_template(
        "sifremi_unuttum.html",
        hata=hata,
        basari=basari,
        form_data=form_data
    )

@app.route("/sifre-sifirla/<token>", methods=["GET", "POST"])
def sifre_sifirla(token):
    hata = None
    basari = None
    gecersiz = False

    token_hash = sifre_sifirlama_token_hash_olustur(token)

    baglanti = baglanti_olustur()

    try:
        kayit = baglanti.execute("""
            SELECT
                ss.id,
                ss.kullanici_id,
                ss.son_kullanma_tarihi,
                ss.kullanildi,
                k.ad,
                k.soyad
            FROM sifre_sifirlama ss
            JOIN kullanicilar k
                ON ss.kullanici_id = k.id
            WHERE ss.token_hash = ?
        """, (token_hash,)).fetchone()

    finally:
        baglanti.close()

    if not kayit:
        gecersiz = True
        hata = "Şifre sıfırlama bağlantısı geçersizdir."

    elif kayit["kullanildi"] == 1:
        gecersiz = True
        hata = (
            "Bu şifre sıfırlama bağlantısı "
            "daha önce kullanılmıştır."
        )

    else:
        try:
            son_kullanma_tarihi = datetime.strptime(
                kayit["son_kullanma_tarihi"],
                "%Y-%m-%d %H:%M:%S"
            )

            if datetime.now() > son_kullanma_tarihi:
                gecersiz = True
                hata = (
                    "Bu şifre sıfırlama bağlantısının "
                    "süresi dolmuştur."
                )

        except ValueError:
            gecersiz = True
            hata = "Şifre sıfırlama bağlantısı geçersizdir."

    if request.method == "POST" and not gecersiz:
        yeni_sifre = request.form.get(
            "yeni_sifre",
            ""
        )

        yeni_sifre_tekrar = request.form.get(
            "yeni_sifre_tekrar",
            ""
        )

        if not yeni_sifre or not yeni_sifre_tekrar:
            hata = "Lütfen tüm alanları doldurunuz."

        elif yeni_sifre != yeni_sifre_tekrar:
            hata = "Girdiğiniz şifreler birbiriyle eşleşmiyor."

        elif not sifre_kurallarina_uygun_mu(yeni_sifre):
            hata = (
                "Şifre en az 8 karakter olmalı; "
                "büyük harf, küçük harf, rakam "
                "ve özel karakter içermelidir."
            )

        else:
            baglanti = baglanti_olustur()

            try:
                imlec = baglanti.cursor()

                aktif_kayit = imlec.execute("""
                    SELECT
                        kullanici_id,
                        son_kullanma_tarihi
                    FROM sifre_sifirlama
                    WHERE id = ?
                      AND kullanildi = 0
                """, (kayit["id"],)).fetchone()

                if not aktif_kayit:
                    baglanti.rollback()
                    gecersiz = True
                    hata = (
                        "Bu şifre sıfırlama bağlantısı "
                        "artık geçerli değildir."
                    )

                else:
                    son_kullanma_tarihi = datetime.strptime(
                        aktif_kayit["son_kullanma_tarihi"],
                        "%Y-%m-%d %H:%M:%S"
                    )

                    if datetime.now() > son_kullanma_tarihi:
                        baglanti.rollback()
                        gecersiz = True
                        hata = (
                            "Bu şifre sıfırlama bağlantısının "
                            "süresi dolmuştur."
                        )

                    else:
                        imlec.execute("""
                            UPDATE kullanicilar
                            SET sifre = ?
                            WHERE id = ?
                        """, (
                            generate_password_hash(yeni_sifre),
                            kayit["kullanici_id"]
                        ))

                        imlec.execute("""
                            UPDATE sifre_sifirlama
                            SET kullanildi = 1
                            WHERE kullanici_id = ?
                              AND kullanildi = 0
                        """, (
                            kayit["kullanici_id"],
                        ))

                        baglanti.commit()

                        basari = (
                            "Şifreniz başarıyla değiştirildi. "
                            "Yeni şifrenizle giriş yapabilirsiniz."
                        )

            except Exception:
                baglanti.rollback()
                app.logger.exception(
                    "Şifre sıfırlama işlemi başarısız oldu."
                )
                hata = (
                    "Şifre değiştirilirken bir hata oluştu. "
                    "Lütfen tekrar deneyiniz."
                )

            finally:
                baglanti.close()

    return render_template(
        "sifre_sifirla.html",
        hata=hata,
        basari=basari,
        gecersiz=gecersiz
    )

@app.route("/guvenlik-kodu-yenile")
def guvenlik_kodu_yenile():
    guvenlik_kodu_uret()

    return jsonify({
        "guvenlik_kodu": session["guvenlik_kodu"]
    })

def hasta_panel_doktorlarini_getir():
    baglanti = baglanti_olustur()

    doktor_satirlari = baglanti.execute("""
        SELECT
            d.id,
            d.doktor_adi,
            d.poliklinik
        FROM doktorlar d
        JOIN kullanicilar k
            ON d.kullanici_id = k.id
        WHERE k.rol = ?
          AND k.durum = ?
          AND d.durum = ?
        ORDER BY d.doktor_adi COLLATE NOCASE ASC
    """, (
        "doktor",
        "aktif",
        "aktif"
    )).fetchall()

    baglanti.close()

    return [
        {
            "id": doktor["id"],
            "doktor_adi": doktor["doktor_adi"],
            "brans": doktor["poliklinik"]
        }
        for doktor in doktor_satirlari
    ]

def doktor_bransi_getir(doktor_adi):
    baglanti = baglanti_olustur()

    doktor = baglanti.execute("""
        SELECT poliklinik
        FROM doktorlar
        WHERE doktor_adi = ?
    """, (doktor_adi,)).fetchone()

    baglanti.close()

    if doktor:
        return doktor["poliklinik"]

    return None

def hasta_yogunluk_raporlari_getir(secili_tarih):
    aktif_randevu_sayilari = (
        poliklinik_aktif_randevu_sayilari_getir(
            secili_tarih
        )
    )

    raporlar = []

    for poliklinik, aktif_randevu_sayisi in aktif_randevu_sayilari.items():

        if aktif_randevu_sayisi < 3:
            yogunluk = "Düşük"
            yogunluk_class = "hasta-yogunluk-dusuk"
            cubuk_class = "hasta-cubuk-dusuk"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu düşük seviyededir."
            )

        elif aktif_randevu_sayisi <= 5:
            yogunluk = "Orta"
            yogunluk_class = "hasta-yogunluk-orta"
            cubuk_class = "hasta-cubuk-orta"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu orta seviyededir."
            )

        else:
            yogunluk = "Yüksek"
            yogunluk_class = "hasta-yogunluk-yuksek"
            cubuk_class = "hasta-cubuk-yuksek"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu yüksek seviyededir."
            )

        raporlar.append({
            "poliklinik": poliklinik,
            "aktif_randevu_sayisi": aktif_randevu_sayisi,
            "yogunluk": yogunluk,
            "yogunluk_class": yogunluk_class,
            "cubuk_class": cubuk_class,
            "aciklama": aciklama
        })

    return raporlar

def poliklinik_aktif_randevu_sayilari_getir(secili_tarih):
    poliklinikler = [
        "Dahiliye",
        "Kardiyoloji",
        "Göz Hastalıkları",
        "Ortopedi",
        "Dermatoloji"
    ]

    sayilar = {
        poliklinik: 0
        for poliklinik in poliklinikler
    }

    baglanti = baglanti_olustur()

    satirlar = baglanti.execute("""
        SELECT
            poliklinik,
            COUNT(*) AS aktif_randevu_sayisi
        FROM randevular
        WHERE tarih = ?
          AND durum = ?
        GROUP BY poliklinik
    """, (
        secili_tarih,
        "aktif"
    )).fetchall()

    baglanti.close()

    for satir in satirlar:
        poliklinik = satir["poliklinik"]

        if poliklinik in sayilar:
            sayilar[poliklinik] = satir["aktif_randevu_sayisi"]

    return sayilar

@app.route("/hasta-panel")
def hasta_panel():
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    kullanici_id = aktif_kullanici_id_getir()

    kullanici = kullanici_bilgilerini_id_ile_getir(
        kullanici_id
    )

    if not kullanici or kullanici["rol"] != "hasta":
        session.clear()
        return redirect(url_for("giris"))

    kullanici_anahtar = (
        kullanici["tc_no"]
        or kullanici["email"]
    )

    tum_randevular = hasta_randevularini_getir()
    aktif_randevular = hasta_aktif_randevularini_getir()
    iptal_randevular = hasta_iptal_randevularini_getir()
    bekleme_kayitlari = hasta_bekleme_kayitlarini_getir()

    aktif_bolum = request.args.get("bolum", "anasayfa")

    hasta_yogunluk_tarihi = request.args.get("yogunluk_tarihi", date.today().isoformat()).strip()

    try:
        datetime.strptime(hasta_yogunluk_tarihi, "%Y-%m-%d")
    except ValueError:
        hasta_yogunluk_tarihi = date.today().isoformat()

    hasta_yogunluk_raporlari = hasta_yogunluk_raporlari_getir(hasta_yogunluk_tarihi)
    bugunun_yogunluk_raporlari = hasta_yogunluk_raporlari_getir(date.today().isoformat())

    hasta_bugun_orta_yogunluk_sayisi = len([
        rapor for rapor in bugunun_yogunluk_raporlari
        if rapor.get("yogunluk") == "Orta"
    ])

    hasta_bugun_yuksek_yogunluk_sayisi = len([
        rapor for rapor in bugunun_yogunluk_raporlari
        if rapor.get("yogunluk") == "Yüksek"
    ])

    return render_template(
        "hasta_panel.html",
        kullanici=kullanici,
        kullanici_anahtar=kullanici_anahtar,
        randevular=tum_randevular,
        aktif_randevular=aktif_randevular,
        iptal_randevular=iptal_randevular,
        bekleme_kayitlari=bekleme_kayitlari,
        aktif_bolum=aktif_bolum,
        bugun=date.today().isoformat(),
        hasta_panel_doktorlar=hasta_panel_doktorlarini_getir(),
        hasta_yogunluk_raporlari=hasta_yogunluk_raporlari,
        hasta_yogunluk_tarihi=hasta_yogunluk_tarihi,
        hasta_yogunluk_tarihi_goster=tarih_goster(hasta_yogunluk_tarihi),
        hasta_bugun_orta_yogunluk_sayisi=hasta_bugun_orta_yogunluk_sayisi,
        hasta_bugun_yuksek_yogunluk_sayisi=hasta_bugun_yuksek_yogunluk_sayisi
    )

@app.route("/dolu-saatler")
def dolu_saatler():
    if not giris_kontrol():
        return jsonify({
            "dolu_saatler": [],
            "uygun_saatler": []
        })

    doktor = request.args.get("doktor", "").strip()
    tarih = request.args.get("tarih", "").strip()

    if not doktor or not tarih:
        return jsonify({
            "dolu_saatler": [],
            "uygun_saatler": []
        })

    dolu_saatler_listesi = sqlite_dolu_saatleri_getir(doktor, tarih)

    return jsonify({
        "dolu_saatler": dolu_saatler_listesi,
        "uygun_saatler": doktor_uygun_randevu_saatleri_getir(
            doktor
        )
    })

def sqlite_doktor_id_getir(doktor_adi):
    baglanti = baglanti_olustur()
    doktor = baglanti.execute("""
        SELECT id
        FROM doktorlar
        WHERE doktor_adi = ?
    """, (doktor_adi,)).fetchone()
    baglanti.close()

    if doktor:
        return doktor["id"]

    return None

def sqlite_randevu_kaydet(
    hasta_id,
    doktor_id,
    poliklinik,
    tarih,
    saat,
    hasta_notu
):
    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    try:
        imlec.execute("""
            INSERT INTO randevular
            (
                hasta_id,
                doktor_id,
                poliklinik,
                tarih,
                saat,
                durum,
                hasta_notu,
                doktor_notu
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hasta_id,
            doktor_id,
            poliklinik,
            tarih,
            saat,
            "aktif",
            hasta_notu,
            ""
        ))

        yeni_randevu_id = imlec.lastrowid

        imlec.execute("""
            UPDATE bekleme_listesi
            SET durum = 'randevu_alindi'
            WHERE hasta_id = ?
              AND doktor_id = ?
              AND tarih = ?
              AND saat = ?
              AND durum = 'beklemede'
        """, (
            hasta_id,
            doktor_id,
            tarih,
            saat
        ))

        baglanti.commit()

        return yeni_randevu_id

    except Exception:
        baglanti.rollback()
        raise

    finally:
        baglanti.close()

@app.route("/randevu-olustur", methods=["POST"])
def randevu_olustur():
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    poliklinik = request.form.get("poliklinik", "").strip()
    doktor = request.form.get("doktor", "").strip()
    tarih = request.form.get("tarih", "").strip()
    saat = request.form.get("saat", "").strip()
    hasta_notu = request.form.get("hasta_notu", "").strip()

    if not poliklinik or not doktor or not tarih or not saat:
        flash("Lütfen randevu oluşturmak için tüm alanları doldurunuz.", "hata")
        return redirect(url_for("hasta_panel", bolum="randevu-al"))

    if len(hasta_notu) > 500:
        flash("Randevu notu en fazla 500 karakter olabilir.", "hata")
        return redirect(url_for("hasta_panel", bolum="randevu-al"))

    if not doktor_aktif_mi(doktor):
        flash(
            "Seçilen doktor aktif durumda olmadığı için "
            "randevu oluşturulamaz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )

    doktor_bransi = doktor_bransi_getir(doktor)

    if doktor_bransi != poliklinik:
        flash("Seçilen doktor, seçilen polikliniğe ait değildir.", "hata")
        return redirect(url_for("hasta_panel", bolum="randevu-al"))

    zaman_gecerli, zaman_hatasi = randevu_zamani_dogrula(
        tarih,
        saat
    )

    if not zaman_gecerli:
        flash(
            zaman_hatasi,
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )

    if not doktor_calisma_saatinde_mi(
        doktor,
        saat
    ):
        flash(
            "Seçilen saat doktorun çalışma "
            "saatleri dışındadır.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )

    if randevu_saati_dolu_mu(doktor, tarih, saat):
        flash("Seçilen doktor için bu tarih ve saatte aktif bir randevu bulunmaktadır.", "hata")
        return redirect(url_for("hasta_panel", bolum="randevu-al"))

    hasta_id = aktif_hasta_id_getir()

    if hasta_ayni_saatte_aktif_randevusu_var_mi(
        hasta_id,
        tarih,
        saat
    ):
        flash(
            "Bu tarih ve saatte başka bir aktif "
            "randevunuz bulunmaktadır.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )
    
    doktor_id = sqlite_doktor_id_getir(doktor)

    if not hasta_id:
        flash(
            "Hasta veritabanı kaydı bulunamadı. Lütfen tekrar giriş yapınız.",
            "hata"
        )
        return redirect(url_for("giris"))

    if not doktor_id:
        flash("Seçilen doktor veritabanında bulunamadı.", "hata")
        return redirect(url_for("hasta_panel", bolum="randevu-al"))

    try:
        sqlite_randevu_kaydet(
            hasta_id,
            doktor_id,
            poliklinik,
            tarih,
            saat,
            hasta_notu
        )

    except sqlite3.IntegrityError:
        flash(
            "Bu randevu saati başka bir hasta "
            "tarafından alınmıştır. Lütfen başka "
            "bir saat seçiniz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )

    except Exception:
        app.logger.exception(
            "Randevu oluşturma sırasında hata oluştu."
        )

        flash(
            "Randevu oluşturulurken bir hata oluştu.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="randevu-al"
            )
        )

    flash(
        "Randevunuz başarıyla oluşturuldu.",
        "basari"
    )

    return redirect(
        url_for(
            "hasta_panel",
            bolum="randevularim"
        )
    )

def sqlite_dolu_saatleri_getir(doktor, tarih):
    doktor_id = sqlite_doktor_id_getir(doktor)

    if not doktor_id:
        return []

    baglanti = baglanti_olustur()
    dolu_saatler = baglanti.execute("""
        SELECT saat
        FROM randevular
        WHERE doktor_id = ?
          AND tarih = ?
          AND durum = ?
    """, (
        doktor_id,
        tarih,
        "aktif"
    )).fetchall()
    baglanti.close()

    return [kayit["saat"] for kayit in dolu_saatler]

def hasta_ayni_saatte_aktif_randevusu_var_mi(
    hasta_id,
    tarih,
    saat
):
    if not hasta_id:
        return False

    baglanti = baglanti_olustur()

    try:
        randevu = baglanti.execute("""
            SELECT id
            FROM randevular
            WHERE hasta_id = ?
              AND tarih = ?
              AND saat = ?
              AND durum = 'aktif'
            LIMIT 1
        """, (
            hasta_id,
            tarih,
            saat
        )).fetchone()

        return randevu is not None

    finally:
        baglanti.close()

@app.route(
    "/randevu-iptal/<int:randevu_id>",
    methods=["POST"]
)
def randevu_iptal(randevu_id):
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    hasta_id = aktif_hasta_id_getir()

    if not hasta_id:
        flash(
            "Hasta bilgisi bulunamadı. "
            "Lütfen tekrar giriş yapınız.",
            "hata"
        )

        return redirect(url_for("giris"))

    baglanti = baglanti_olustur()

    bosalan_randevu = None

    try:
        randevu = baglanti.execute("""
            SELECT
                id,
                doktor_id,
                poliklinik,
                tarih,
                saat,
                durum
            FROM randevular
            WHERE id = ?
              AND hasta_id = ?
        """, (
            randevu_id,
            hasta_id
        )).fetchone()

        if not randevu:
            flash(
                "İptal edilecek randevu bulunamadı.",
                "hata"
            )

        elif randevu["durum"] == "iptal_edildi":
            flash(
                "Bu randevu zaten iptal edilmiş.",
                "hata"
            )

        else:
            baglanti.execute("""
                UPDATE randevular
                SET durum = 'iptal_edildi'
                WHERE id = ?
                  AND hasta_id = ?
            """, (
                randevu_id,
                hasta_id
            ))

            baglanti.commit()

            bosalan_randevu = {
                "doktor_id": randevu["doktor_id"],
                "poliklinik": randevu["poliklinik"],
                "tarih": randevu["tarih"],
                "saat": randevu["saat"]
            }

            flash(
                "Randevunuz başarıyla iptal edildi.",
                "basari"
            )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Hasta randevu iptal işlemi sırasında "
            "hata oluştu."
        )

        flash(
            "Randevu iptal edilirken bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    if bosalan_randevu:

        sonuc = bosalan_randevu_bildirimlerini_gonder(
            bosalan_randevu["doktor_id"],
            bosalan_randevu["poliklinik"],
            bosalan_randevu["tarih"],
            bosalan_randevu["saat"]
        )

        if sonuc["gonderilen"] > 0:
            flash(
                f"Bekleme listesindeki "
                f"{sonuc['gonderilen']} hastaya "
                f"e-posta bildirimi gönderildi.",
                "basari"
            )

        elif sonuc["bekleyen"] > 0:
            flash(
                "Randevu iptal edildi ancak "
                "e-posta bildirimi gönderilemedi. "
                "SMTP ayarlarını kontrol ediniz.",
                "hata"
            )

    return redirect(
        url_for(
            "hasta_panel",
            bolum="randevularim"
        )
    )

@app.route("/bekleme-listesine-katil", methods=["POST"])
def bekleme_listesine_katil():
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    poliklinik = request.form.get(
        "poliklinik", ""
    ).strip()

    doktor = request.form.get(
        "doktor", ""
    ).strip()

    tarih = request.form.get(
        "tarih", ""
    ).strip()

    saat = request.form.get(
        "saat", ""
    ).strip()

    if not poliklinik or not doktor or not tarih or not saat:
        flash(
            "Bekleme listesine katılmak için "
            "poliklinik, doktor, tarih ve dolu saat seçiniz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if not doktor_aktif_mi(doktor):
        flash(
            "Seçilen doktor aktif durumda değildir.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    hasta_id = aktif_hasta_id_getir()
    doktor_id = sqlite_doktor_id_getir(doktor)

    if not hasta_id:
        flash(
            "Hasta bilgileri bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if not doktor_id:
        flash(
            "Seçilen doktor veritabanında bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    doktor_bransi = doktor_bransi_getir(doktor)

    if doktor_bransi != poliklinik:
        flash(
            "Seçilen doktor, seçilen polikliniğe ait değildir.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    zaman_gecerli, zaman_hatasi = randevu_zamani_dogrula(
        tarih,
        saat
    )

    if not zaman_gecerli:
        flash(
            zaman_hatasi,
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if not doktor_calisma_saatinde_mi(
        doktor,
        saat
    ):
        flash(
            "Seçilen saat doktorun çalışma "
            "saatleri dışındadır.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if not randevu_saati_dolu_mu(
        doktor,
        tarih,
        saat
    ):
        flash(
            "Bekleme listesine yalnızca "
            "dolu randevu saatleri için katılabilirsiniz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if hastanin_aktif_randevusu_var_mi(
        doktor,
        tarih,
        saat
    ):
        flash(
            "Bu tarih ve saatte zaten aktif "
            "randevunuz bulunduğu için "
            "bekleme listesine katılamazsınız.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    if bekleme_kaydi_var_mi(
        doktor,
        tarih,
        saat
    ):
        flash(
            "Bu randevu saati için zaten aktif "
            "bir bekleme listesi kaydınız bulunmaktadır.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    baglanti = baglanti_olustur()

    try:
        baglanti.execute("""
            INSERT INTO bekleme_listesi
            (
                hasta_id,
                doktor_id,
                poliklinik,
                tarih,
                saat,
                durum
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            hasta_id,
            doktor_id,
            poliklinik,
            tarih,
            saat,
            "beklemede"
        ))

        baglanti.commit()

        flash(
            "Bekleme listesine başarıyla katıldınız.",
            "basari"
        )

    except sqlite3.IntegrityError:
        baglanti.rollback()

        flash(
            "Bu randevu saati için zaten aktif "
            "bir bekleme listesi kaydınız bulunmaktadır.",
            "hata"
        )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Bekleme listesine katılma sırasında hata oluştu."
        )

        flash(
            "Bekleme listesine kayıt sırasında bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    return redirect(
        url_for(
            "hasta_panel",
            bolum="bekleme"
        )
    )

@app.route(
    "/bekleme-listesinden-cik/<int:kayit_id>",
    methods=["POST"]
)
def bekleme_listesinden_cik(kayit_id):
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    hasta_id = aktif_hasta_id_getir()

    if not hasta_id:
        flash(
            "Hasta bilgileri bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="bekleme"
            )
        )

    baglanti = baglanti_olustur()

    try:
        kayit = baglanti.execute("""
            SELECT
                id,
                durum
            FROM bekleme_listesi
            WHERE id = ?
              AND hasta_id = ?
        """, (
            kayit_id,
            hasta_id
        )).fetchone()

        if not kayit:
            flash(
                "Bekleme listesi kaydı bulunamadı.",
                "hata"
            )

        elif kayit["durum"] != "beklemede":
            flash(
                "Bu bekleme listesi kaydından zaten çıkılmış.",
                "hata"
            )

        else:
            baglanti.execute("""
                UPDATE bekleme_listesi
                SET durum = ?
                WHERE id = ?
                  AND hasta_id = ?
            """, (
                "listeden_cikildi",
                kayit_id,
                hasta_id
            ))

            baglanti.commit()

            flash(
                "Bekleme listesi kaydınız kaldırıldı.",
                "basari"
            )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Bekleme listesinden çıkma sırasında hata oluştu."
        )

        flash(
            "Bekleme listesi kaydı kaldırılırken "
            "bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    return redirect(
        url_for(
            "hasta_panel",
            bolum="bekleme"
        )
    )

@app.route("/profil-guncelle", methods=["POST"])
def profil_guncelle():
    if not giris_kontrol("hasta"):
        return redirect(url_for("giris"))

    kullanici_id = aktif_kullanici_id_getir()

    kullanici = kullanici_bilgilerini_id_ile_getir(
        kullanici_id
    )

    if not kullanici or kullanici["rol"] != "hasta":
        flash(
            "Kullanıcı bilgileri bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    telefon_girisi = request.form.get(
        "telefon", ""
    ).strip()

    email = request.form.get(
        "email", ""
    ).strip().lower()

    mevcut_sifre = request.form.get(
        "mevcut_sifre", ""
    ).strip()

    yeni_sifre = request.form.get(
        "yeni_sifre", ""
    ).strip()

    yeni_sifre_tekrar = request.form.get(
        "yeni_sifre_tekrar", ""
    ).strip()

    telefon_rakamlar = re.sub(
        r"\D",
        "",
        telefon_girisi
    )

    if not telefon_girisi or not email:
        flash(
            "Telefon ve e-posta alanları boş bırakılamaz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    if len(telefon_rakamlar) not in [10, 11]:
        flash(
            "Telefon numarası 10 veya 11 haneli olmalıdır.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    if not email_gecerli_mi(email):
        flash(
            "Geçerli bir e-posta adresi giriniz.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    if email_baska_kullanicida_mi(
        email,
        kullanici_id
    ):
        flash(
            "Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    sifre_degistirilecek = bool(
        yeni_sifre
        or yeni_sifre_tekrar
        or mevcut_sifre
    )

    if sifre_degistirilecek:

        if (
            not mevcut_sifre
            or not yeni_sifre
            or not yeni_sifre_tekrar
        ):
            flash(
                "Şifre değiştirmek için mevcut şifre, "
                "yeni şifre ve yeni şifre tekrarı "
                "alanlarını doldurunuz.",
                "hata"
            )

            return redirect(
                url_for(
                    "hasta_panel",
                    bolum="profil"
                )
            )

        if not check_password_hash(
            kullanici["sifre"],
            mevcut_sifre
        ):
            flash(
                "Mevcut şifreniz hatalı.",
                "hata"
            )

            return redirect(
                url_for(
                    "hasta_panel",
                    bolum="profil"
                )
            )

        if yeni_sifre != yeni_sifre_tekrar:
            flash(
                "Yeni şifre ve yeni şifre tekrarı eşleşmiyor.",
                "hata"
            )

            return redirect(
                url_for(
                    "hasta_panel",
                    bolum="profil"
                )
            )

        if check_password_hash(
            kullanici["sifre"],
            yeni_sifre
        ):
            flash(
                "Yeni şifre mevcut şifre ile aynı olamaz.",
                "hata"
            )

            return redirect(
                url_for(
                    "hasta_panel",
                    bolum="profil"
                )
            )

        if not sifre_kurallarina_uygun_mu(
            yeni_sifre
        ):
            flash(
                "Yeni şifre en az 8 karakter olmalı; "
                "büyük harf, küçük harf, rakam ve "
                "sembol içermelidir.",
                "hata"
            )

            return redirect(
                url_for(
                    "hasta_panel",
                    bolum="profil"
                )
            )

    telefon = telefon_formatla(
        telefon_rakamlar
    )

    baglanti = baglanti_olustur()

    try:
        if sifre_degistirilecek:
            baglanti.execute("""
                UPDATE kullanicilar
                SET
                    telefon = ?,
                    email = ?,
                    sifre = ?
                WHERE id = ?
                  AND rol = 'hasta'
            """, (
                telefon,
                email,
                generate_password_hash(yeni_sifre),
                kullanici_id
            ))

        else:
            baglanti.execute("""
                UPDATE kullanicilar
                SET
                    telefon = ?,
                    email = ?
                WHERE id = ?
                  AND rol = 'hasta'
            """, (
                telefon,
                email,
                kullanici_id
            ))

        baglanti.commit()

    except sqlite3.IntegrityError:
        baglanti.rollback()

        flash(
            "Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Hasta profil güncelleme sırasında hata oluştu."
        )

        flash(
            "Profil bilgileri güncellenirken bir hata oluştu.",
            "hata"
        )

        return redirect(
            url_for(
                "hasta_panel",
                bolum="profil"
            )
        )

    finally:
        baglanti.close()

    oturum_bilgilerini_yenile(
        kullanici_id
    )

    flash(
        "Profil bilgileriniz başarıyla güncellendi.",
        "basari"
    )

    return redirect(
        url_for(
            "hasta_panel",
            bolum="profil"
        )
    )

@app.route("/doktor-panel")
def doktor_panel():
    if not giris_kontrol("doktor"):
        return redirect(url_for("giris"))

    doktor_bilgileri = doktor_bilgilerini_getir()

    if not doktor_bilgileri:
        session.clear() 
        return redirect(url_for("giris"))

    doktor_adi = doktor_bilgileri["doktor_adi"]
    
    tum_randevular = doktor_randevularini_getir(doktor_adi)

    aktif_randevular = [
        randevu for randevu in tum_randevular
        if randevu["durum"] == "Aktif"
    ]

    iptal_randevular = [
        randevu for randevu in tum_randevular
        if randevu["durum"] == "İptal Edildi"
    ]

    bugun = date.today().isoformat()

    secili_tarih = request.args.get("tarih", bugun).strip()

    try:
        datetime.strptime(secili_tarih, "%Y-%m-%d")
    except ValueError:
        secili_tarih = bugun

    secili_tarih_randevulari = [
        randevu for randevu in aktif_randevular
        if randevu["tarih"] == secili_tarih
    ]

    bugunku_randevular = [
        randevu for randevu in aktif_randevular
        if randevu["tarih"] == bugun
    ]

    aktif_bolum = request.args.get("bolum", "doktor-anasayfa")

    izinli_doktor_bolumler = [
        "doktor-anasayfa",
        "gunluk-randevular",
        "randevu-detaylari",
        "iptal-randevular",
        "doktor-profil"
    ]

    if aktif_bolum not in izinli_doktor_bolumler:
        aktif_bolum = "doktor-anasayfa"

    secili_randevu_id = request.args.get("randevu_id", type=int)

    secili_randevu = None

    if secili_randevu_id:
        for randevu in tum_randevular:
            if randevu["id"] == secili_randevu_id:
                secili_randevu = randevu
                break

    if not secili_randevu and secili_tarih_randevulari:
        secili_randevu = secili_tarih_randevulari[0]

    return render_template(
        "doktor_panel.html",
        doktor_bilgileri=doktor_bilgileri,
        tum_randevular=tum_randevular,
        aktif_randevular=aktif_randevular,
        iptal_randevular=iptal_randevular,
        bugunku_randevular=bugunku_randevular,
        secili_tarih=secili_tarih,
        secili_tarih_goster=tarih_goster(secili_tarih),
        secili_tarih_randevulari=secili_tarih_randevulari,
        secili_randevu=secili_randevu,
        aktif_bolum=aktif_bolum,
        bugun_goster=tarih_goster(bugun)
    )

@app.route("/doktor-not-guncelle/<int:randevu_id>", methods=["POST"])
def doktor_not_guncelle(randevu_id):
    if not giris_kontrol("doktor"):
        return redirect(url_for("giris"))

    doktor_notu = request.form.get("doktor_notu", "").strip()
    tarih = request.form.get("tarih", date.today().isoformat()).strip()
    donus_bolum = request.form.get("donus_bolum", "gunluk-randevular").strip()

    izinli_bolumler = [
        "gunluk-randevular",
        "randevu-detaylari",
        "iptal-randevular"
    ]

    if donus_bolum not in izinli_bolumler:
        donus_bolum = "gunluk-randevular"

    if len(doktor_notu) > 1000:
        flash("Doktor notu en fazla 1000 karakter olabilir.", "hata")

        if donus_bolum == "randevu-detaylari":
            return redirect(url_for(
                "doktor_panel",
                bolum="randevu-detaylari",
                randevu_id=randevu_id,
                tarih=tarih
            ))

        return redirect(url_for(
            "doktor_panel",
            bolum=donus_bolum,
            tarih=tarih
        ))

    basarili = sqlite_doktor_notu_guncelle(randevu_id, doktor_notu)

    if basarili:
        if doktor_notu:
            flash("Doktor notu başarıyla kaydedildi.", "basari")
        else:
            flash("Doktor notu temizlendi.", "basari")
    else:
        flash("Not eklenecek randevu bulunamadı.", "hata")

    if donus_bolum == "randevu-detaylari":
        return redirect(url_for(
            "doktor_panel",
            bolum="randevu-detaylari",
            randevu_id=randevu_id,
            tarih=tarih
        ))

    return redirect(url_for(
        "doktor_panel",
        bolum=donus_bolum,
        tarih=tarih
    ))

@app.route("/doktor-profil-guncelle", methods=["POST"])
def doktor_profil_guncelle():
    if not giris_kontrol("doktor"):
        return redirect(url_for("giris"))

    kullanici_id = aktif_kullanici_id_getir()

    kullanici = kullanici_bilgilerini_id_ile_getir(
        kullanici_id
    )

    if not kullanici or kullanici["rol"] != "doktor":
        flash(
            "Doktor bilgileri bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    telefon_girisi = request.form.get(
        "telefon", ""
    ).strip()

    email = request.form.get(
        "email", ""
    ).strip().lower()

    calisma_saatleri = request.form.get(
        "calisma_saatleri", ""
    ).strip()

    mevcut_sifre = request.form.get(
        "mevcut_sifre", ""
    ).strip()

    yeni_sifre = request.form.get(
        "yeni_sifre", ""
    ).strip()

    yeni_sifre_tekrar = request.form.get(
        "yeni_sifre_tekrar", ""
    ).strip()

    telefon_rakamlar = re.sub(
        r"\D",
        "",
        telefon_girisi
    )

    if (
        not telefon_girisi
        or not email
        or not calisma_saatleri
    ):
        flash(
            "Telefon, e-posta ve çalışma saatleri "
            "alanları boş bırakılamaz.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    if len(telefon_rakamlar) not in [10, 11]:
        flash(
            "Telefon numarası 10 veya 11 haneli olmalıdır.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    if not email_gecerli_mi(email):
        flash(
            "Geçerli bir e-posta adresi giriniz.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    if len(calisma_saatleri) > 50:
        flash(
            "Çalışma saatleri en fazla 50 karakter olabilir.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    if not calisma_saatleri_gecerli_mi(
        calisma_saatleri
    ):
        flash(
            "Çalışma saatlerini 09:00 - 17:00 "
            "biçiminde giriniz. Başlangıç saati "
            "bitiş saatinden önce olmalıdır.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    if email_baska_kullanicida_mi(
        email,
        kullanici_id
    ):
        flash(
            "Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    sifre_degistirilecek = bool(
        yeni_sifre
        or yeni_sifre_tekrar
        or mevcut_sifre
    )

    if sifre_degistirilecek:

        if (
            not mevcut_sifre
            or not yeni_sifre
            or not yeni_sifre_tekrar
        ):
            flash(
                "Şifre değiştirmek için mevcut şifre, "
                "yeni şifre ve yeni şifre tekrarı "
                "alanlarını doldurunuz.",
                "hata"
            )

            return redirect(
                url_for(
                    "doktor_panel",
                    bolum="doktor-profil"
                )
            )

        if not check_password_hash(
            kullanici["sifre"],
            mevcut_sifre
        ):
            flash(
                "Mevcut şifreniz hatalı.",
                "hata"
            )
            
            return redirect(
                url_for(
                    "doktor_panel",
                    bolum="doktor-profil"
                )
            )

        if yeni_sifre != yeni_sifre_tekrar:
            flash(
                "Yeni şifre ve yeni şifre tekrarı eşleşmiyor.",
                "hata"
            )

            return redirect(
                url_for(
                    "doktor_panel",
                    bolum="doktor-profil"
                )
            )

        if check_password_hash(
            kullanici["sifre"],
            yeni_sifre
        ):
            flash(
                "Yeni şifre mevcut şifre ile aynı olamaz.",
                "hata"
            )

            return redirect(
                url_for(
                    "doktor_panel",
                    bolum="doktor-profil"
                )
            )

        if not sifre_kurallarina_uygun_mu(
            yeni_sifre
        ):
            flash(
                "Yeni şifre en az 8 karakter olmalı; "
                "büyük harf, küçük harf, rakam ve "
                "sembol içermelidir.",
                "hata"
            )

            return redirect(
                url_for(
                    "doktor_panel",
                    bolum="doktor-profil"
                )
            )

    telefon = telefon_formatla(
        telefon_rakamlar
    )

    baglanti = baglanti_olustur()

    try:
        # Kullanıcı bilgilerini güncelle
        if sifre_degistirilecek:
            baglanti.execute("""
                UPDATE kullanicilar
                SET
                    telefon = ?,
                    email = ?,
                    sifre = ?
                WHERE id = ?
                  AND rol = 'doktor'
            """, (
                telefon,
                email,
                generate_password_hash(yeni_sifre),
                kullanici_id
            ))

        else:
            baglanti.execute("""
                UPDATE kullanicilar
                SET
                    telefon = ?,
                    email = ?
                WHERE id = ?
                  AND rol = 'doktor'
            """, (
                telefon,
                email,
                kullanici_id
            ))

        # Doktor bilgilerini güncelle
        baglanti.execute("""
            UPDATE doktorlar
            SET calisma_saatleri = ?
            WHERE kullanici_id = ?
        """, (
            calisma_saatleri,
            kullanici_id
        ))

        baglanti.commit()

    except sqlite3.IntegrityError:
        baglanti.rollback()

        flash(
            "Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Doktor profil güncelleme sırasında hata oluştu."
        )

        flash(
            "Doktor profil bilgileri güncellenirken "
            "bir hata oluştu.",
            "hata"
        )

        return redirect(
            url_for(
                "doktor_panel",
                bolum="doktor-profil"
            )
        )

    finally:
        baglanti.close()

    oturum_bilgilerini_yenile(
        kullanici_id
    )

    flash(
        "Doktor profil bilgileri başarıyla güncellendi.",
        "basari"
    )

    return redirect(
        url_for(
            "doktor_panel",
            bolum="doktor-profil"
        )
    )

def admin_hastalari_getir():
    baglanti = baglanti_olustur()

    hasta_satirlari = baglanti.execute("""
        SELECT
            id,
            tc_no,
            ad,
            soyad,
            dogum_tarihi,
            email,
            telefon,
            durum
        FROM kullanicilar
        WHERE rol = ?
        ORDER BY ad COLLATE NOCASE ASC,
                 soyad COLLATE NOCASE ASC
    """, ("hasta",)).fetchall()

    baglanti.close()

    admin_hastalar = []

    for hasta in hasta_satirlari:
        ad_soyad = (
            f"{hasta['ad'] or ''} "
            f"{hasta['soyad'] or ''}"
        ).strip()

        if hasta["dogum_tarihi"]:
            dogum_tarihi = tarih_goster(
                hasta["dogum_tarihi"]
            )
        else:
            dogum_tarihi = "Belirtilmedi"

        durum = (
            "Aktif"
            if hasta["durum"] == "aktif"
            else "Pasif"
        )

        admin_hastalar.append({
            "id": hasta["id"],
            "anahtar": hasta["id"],
            "tc": hasta["tc_no"] or "Belirtilmedi",
            "ad": hasta["ad"],
            "soyad": hasta["soyad"],
            "ad_soyad": ad_soyad or "Hasta",
            "telefon": hasta["telefon"] or "Belirtilmedi",
            "email": hasta["email"] or "Belirtilmedi",
            "dogum_tarihi": dogum_tarihi,
            "durum": durum
        })

    return admin_hastalar

def doktor_adi_duzenle(doktor_adi):
    doktor_adi = re.sub(r"\s+", " ", doktor_adi.strip())

    if not doktor_adi:
        return doktor_adi

    if doktor_adi.lower().startswith("dr."):
        doktor_adi = "Dr. " + doktor_adi[3:].strip()
    else:
        doktor_adi = "Dr. " + doktor_adi

    return re.sub(r"\s+", " ", doktor_adi).strip()

def doktor_aktif_mi(doktor_adi):
    baglanti = baglanti_olustur()

    doktor = baglanti.execute("""
        SELECT
            d.durum AS doktor_durum,
            k.durum AS kullanici_durum
        FROM doktorlar d
        JOIN kullanicilar k
            ON d.kullanici_id = k.id
        WHERE d.doktor_adi = ?
    """, (doktor_adi,)).fetchone()

    baglanti.close()

    if not doktor:
        return False

    return (
        doktor["doktor_durum"] == "aktif"
        and
        doktor["kullanici_durum"] == "aktif"
    )

def admin_doktorlari_getir():
    baglanti = baglanti_olustur()

    doktor_satirlari = baglanti.execute("""
        SELECT
            d.id AS doktor_id,
            d.kullanici_id,
            d.doktor_adi,
            d.poliklinik,
            d.calisma_saatleri,
            d.durum AS doktor_durum,

            k.tc_no,
            k.ad,
            k.soyad,
            k.telefon,
            k.email,
            k.durum AS kullanici_durum

        FROM doktorlar d

        JOIN kullanicilar k
            ON d.kullanici_id = k.id

        WHERE k.rol = ?

        ORDER BY d.doktor_adi COLLATE NOCASE ASC
    """, ("doktor",)).fetchall()

    baglanti.close()

    doktorlar = []

    for doktor in doktor_satirlari:
        aktif_mi = (
            doktor["doktor_durum"] == "aktif"
            and
            doktor["kullanici_durum"] == "aktif"
        )

        doktorlar.append({
            "id": doktor["doktor_id"],
            "kullanici_id": doktor["kullanici_id"],
            "tc": doktor["tc_no"] or "Belirtilmedi",
            "doktor_adi": doktor["doktor_adi"],
            "brans": doktor["poliklinik"],
            "telefon": doktor["telefon"] or "Belirtilmedi",
            "email": doktor["email"] or "Belirtilmedi",
            "calisma_saatleri": (
                doktor["calisma_saatleri"]
                or "09:00 - 17:00"
            ),
            "durum": "Aktif" if aktif_mi else "Pasif"
        })

    return doktorlar

def admin_aktif_doktorlari_getir():
    return [
        doktor
        for doktor in admin_doktorlari_getir()
        if doktor["durum"] == "Aktif"
    ]

#06.08
def admin_randevulari_getir():
    baglanti = baglanti_olustur()

    try:
        randevu_satirlari = baglanti.execute("""
            SELECT
                r.id,
                r.poliklinik,
                r.tarih,
                r.saat,
                r.durum,
                r.hasta_notu,
                r.doktor_notu,
                r.olusturma_tarihi,

                h.ad AS hasta_ad,
                h.soyad AS hasta_soyad,
                h.tc_no AS hasta_tc,
                h.telefon AS hasta_telefon,
                h.email AS hasta_email,
                h.dogum_tarihi AS hasta_dogum_tarihi,

                d.doktor_adi

            FROM randevular r

            LEFT JOIN kullanicilar h
                ON r.hasta_id = h.id

            LEFT JOIN doktorlar d
                ON r.doktor_id = d.id

            ORDER BY r.olusturma_tarihi DESC, r.id DESC
        """).fetchall()

    finally:
        baglanti.close()

    admin_randevular = []

    for randevu in randevu_satirlari:
        hasta_ad_soyad = (
            f"{randevu['hasta_ad'] or ''} "
            f"{randevu['hasta_soyad'] or ''}"
        ).strip()

        if randevu["durum"] == "iptal_edildi":
            durum_goster = "İptal Edildi"
        else:
            durum_goster = "Aktif"

        admin_randevular.append({
            "id": randevu["id"],

            "hasta": hasta_ad_soyad or "Belirtilmedi",
            "hasta_tc": randevu["hasta_tc"] or "Belirtilmedi",
            "hasta_telefon": randevu["hasta_telefon"] or "Belirtilmedi",
            "hasta_email": randevu["hasta_email"] or "Belirtilmedi",
            "hasta_dogum_tarihi": (
                randevu["hasta_dogum_tarihi"] or "Belirtilmedi"
            ),

            "doktor": randevu["doktor_adi"] or "Belirtilmedi",
            "poliklinik": randevu["poliklinik"],
            "tarih": tarih_goster(randevu["tarih"]),
            "saat": randevu["saat"],
            "durum": durum_goster,

            "hasta_notu": (
                randevu["hasta_notu"] or "Not eklenmedi"
            ),
            "doktor_notu": (
                randevu["doktor_notu"] or "Not eklenmedi"
            ),

            "olusturma_tarihi": randevu["olusturma_tarihi"]
        })

    return admin_randevular

def admin_bekleme_kayitlari_getir():
    baglanti = baglanti_olustur()

    kayit_satirlari = baglanti.execute("""
        SELECT
            b.id,
            b.poliklinik,
            b.tarih,
            b.saat,
            b.durum,
            b.olusturma_tarihi,

            h.tc_no AS hasta_tc,
            h.ad AS hasta_ad,
            h.soyad AS hasta_soyad,
            h.telefon AS hasta_telefon,
            h.email AS hasta_email,
            h.dogum_tarihi AS hasta_dogum_tarihi,

            d.doktor_adi

        FROM bekleme_listesi b

        JOIN kullanicilar h
            ON b.hasta_id = h.id

        JOIN doktorlar d
            ON b.doktor_id = d.id

        ORDER BY
            b.olusturma_tarihi DESC,
            b.id DESC
    """).fetchall()

    baglanti.close()

    admin_kayitlar = []

    for kayit in kayit_satirlari:

        hasta_ad_soyad = (
            f"{kayit['hasta_ad'] or ''} "
            f"{kayit['hasta_soyad'] or ''}"
        ).strip()

        if kayit["durum"] == "beklemede":
            durum_goster = "Beklemede"

        elif kayit["durum"] == "randevu_alindi":
            durum_goster = "Randevu Alındı"

        elif kayit["durum"] == "listeden_cikildi":
            durum_goster = "Listeden Çıkıldı"

        else:
            durum_goster = kayit["durum"]

        admin_kayitlar.append({
            "id": kayit["id"],
            "hasta": hasta_ad_soyad or "Hasta",
            "hasta_tc": (
                kayit["hasta_tc"]
                or "Belirtilmedi"
            ),
            "hasta_telefon": (
                kayit["hasta_telefon"]
                or "Belirtilmedi"
            ),
            "hasta_email": (
                kayit["hasta_email"]
                or "Belirtilmedi"
            ),
            "hasta_dogum_tarihi": (
                tarih_goster(
                    kayit["hasta_dogum_tarihi"]
                )
                if kayit["hasta_dogum_tarihi"]
                else "Belirtilmedi"
            ),
            "doktor": (
                kayit["doktor_adi"]
                or "Belirtilmedi"
            ),
            "poliklinik": kayit["poliklinik"],
            "tarih": tarih_goster(
                kayit["tarih"]
            ),
            "saat": kayit["saat"],
            "durum": durum_goster
        })

    return admin_kayitlar


def admin_yogunluk_raporlari_getir(secili_tarih):
    aktif_randevu_sayilari = (
        poliklinik_aktif_randevu_sayilari_getir(
            secili_tarih
        )
    )

    raporlar = []

    for poliklinik, aktif_randevu_sayisi in aktif_randevu_sayilari.items():

        if aktif_randevu_sayisi <= 2:
            yogunluk = "Düşük"
            yogunluk_class = "admin-yogunluk-dusuk"
            cubuk_class = "admin-cubuk-dusuk"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu düşük seviyededir."
            )

        elif aktif_randevu_sayisi <= 5:
            yogunluk = "Orta"
            yogunluk_class = "admin-yogunluk-orta"
            cubuk_class = "admin-cubuk-orta"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu orta seviyededir."
            )

        else:
            yogunluk = "Yüksek"
            yogunluk_class = "admin-yogunluk-yuksek"
            cubuk_class = "admin-cubuk-yuksek"
            aciklama = (
                "Seçilen tarihte bu poliklinikte "
                "randevu yoğunluğu yüksek seviyededir."
            )

        raporlar.append({
            "poliklinik": poliklinik,
            "aktif_randevu_sayisi": aktif_randevu_sayisi,
            "yogunluk": yogunluk,
            "yogunluk_class": yogunluk_class,
            "cubuk_class": cubuk_class,
            "aciklama": aciklama
        })

    return raporlar

@app.route("/admin-panel")
def admin_panel():
    if not giris_kontrol("yonetici"):
        return redirect(url_for("giris"))

    gecerli_admin_bolumleri = [
        "admin-anasayfa",
        "hasta-yonetimi",
        "doktor-yonetimi",
        "randevu-yonetimi",
        "bekleme-listesi",
        "yogunluk-raporlari"
    ]

    aktif_bolum = request.args.get("bolum", "admin-anasayfa")

    if aktif_bolum not in gecerli_admin_bolumleri:
        aktif_bolum = "admin-anasayfa"

    admin_yogunluk_tarihi = request.args.get("yogunluk_tarihi", date.today().isoformat()).strip()

    try:
        datetime.strptime(admin_yogunluk_tarihi, "%Y-%m-%d")
    except ValueError:
        admin_yogunluk_tarihi = date.today().isoformat()

    admin_hastalar = admin_hastalari_getir()
    admin_doktorlar = admin_doktorlari_getir()
    admin_aktif_doktorlar = admin_aktif_doktorlari_getir()
    admin_randevular = admin_randevulari_getir()
    admin_bekleme_kayitlari = admin_bekleme_kayitlari_getir()
    admin_yogunluk_raporlari = admin_yogunluk_raporlari_getir(admin_yogunluk_tarihi)

    admin_aktif_randevu_sayisi = sum(
        1
        for randevu in admin_randevular
        if randevu["durum"] == "Aktif"
    )

    admin_iptal_randevu_sayisi = sum(
        1
        for randevu in admin_randevular
        if randevu["durum"] == "İptal Edildi"
    )

    admin_son_randevular = admin_randevular[:3]

    return render_template(
        "admin_panel.html",
        aktif_bolum=aktif_bolum,
        admin_hastalar=admin_hastalar,
        admin_doktorlar=admin_doktorlar,
        admin_aktif_doktorlar=admin_aktif_doktorlar,
        admin_randevular=admin_randevular,
        admin_bekleme_kayitlari=admin_bekleme_kayitlari,
        admin_yogunluk_raporlari=admin_yogunluk_raporlari,
        admin_yogunluk_tarihi=admin_yogunluk_tarihi,
        admin_yogunluk_tarihi_goster=tarih_goster(admin_yogunluk_tarihi),
        admin_aktif_randevu_sayisi=admin_aktif_randevu_sayisi,
        admin_iptal_randevu_sayisi=admin_iptal_randevu_sayisi,
        admin_son_randevular=admin_son_randevular,
        bugun=date.today().isoformat()
    )

@app.route("/admin-hasta-randevu-olustur", methods=["POST"])
def admin_hasta_randevu_olustur():
    if not giris_kontrol("yonetici"):
        return redirect(url_for("giris"))

    hasta_id_girisi = request.form.get(
        "hasta_id", ""
    ).strip()

    poliklinik = request.form.get(
        "poliklinik", ""
    ).strip()

    doktor = request.form.get(
        "doktor", ""
    ).strip()

    tarih = request.form.get(
        "tarih", ""
    ).strip()

    saat = request.form.get(
        "saat", ""
    ).strip()

    hasta_notu = request.form.get(
        "hasta_notu", ""
    ).strip()

    if not hasta_id_girisi.isdigit():
        flash(
            "Randevu oluşturulacak hasta bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    hasta_id = int(hasta_id_girisi)

    baglanti = baglanti_olustur()

    hasta = baglanti.execute("""
        SELECT id
        FROM kullanicilar
        WHERE id = ?
          AND rol = ?
          AND durum = ?
    """, (
        hasta_id,
        "hasta",
        "aktif"
    )).fetchone()

    baglanti.close()

    if not hasta:
        flash(
            "Aktif hasta kaydı bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    if (
        not poliklinik
        or not doktor
        or not tarih
        or not saat
    ):
        flash(
            "Randevu oluşturmak için tüm alanları doldurunuz.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    if len(hasta_notu) > 500:
        flash(
            "Randevu notu en fazla 500 karakter olabilir.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    if not doktor_aktif_mi(doktor):
        flash(
            "Seçilen doktor aktif durumda olmadığı için "
            "randevu oluşturulamaz.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    doktor_bransi = doktor_bransi_getir(
        doktor
    )

    if doktor_bransi != poliklinik:
        flash(
            "Seçilen doktor, seçilen polikliniğe ait değildir.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    zaman_gecerli, zaman_hatasi = randevu_zamani_dogrula(
        tarih,
        saat
    )

    if not zaman_gecerli:
        flash(
            zaman_hatasi,
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    if hasta_ayni_saatte_aktif_randevusu_var_mi(
        hasta_id,
        tarih,
        saat
    ):
        flash(
            "Hastanın bu tarih ve saatte başka bir "
            "aktif randevusu bulunmaktadır.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )


    if not doktor_calisma_saatinde_mi(
        doktor,
        saat
    ):
        flash(
            "Seçilen saat doktorun çalışma "
            "saatleri dışındadır.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    if randevu_saati_dolu_mu(
        doktor,
        tarih,
        saat
    ):
        flash(
            "Seçilen doktor için bu tarih ve saatte "
            "aktif bir randevu bulunmaktadır.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    doktor_id = sqlite_doktor_id_getir(
        doktor
    )

    if not doktor_id:
        flash(
            "Seçilen doktor veritabanında bulunamadı.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="hasta-yonetimi"
            )
        )

    try:
        sqlite_randevu_kaydet(
            hasta_id,
            doktor_id,
            poliklinik,
            tarih,
            saat,
            hasta_notu
        )

        flash(
            "Hasta adına randevu başarıyla oluşturuldu.",
            "basari"
        )
    except sqlite3.IntegrityError:
        flash(
            "Bu randevu saati başka bir hasta "
            "tarafından alınmıştır.",
            "hata"
        )
    except Exception:
        app.logger.exception(
            "Admin hasta adına randevu oluştururken hata oluştu."
        )

        flash(
            "Randevu kaydedilirken bir hata oluştu.",
            "hata"
        )

    return redirect(
        url_for(
            "admin_panel",
            bolum="hasta-yonetimi"
        )
    )

@app.route("/admin-doktor-ekle", methods=["POST"])
def admin_doktor_ekle():
    if not giris_kontrol("yonetici"):
        return redirect(url_for("giris"))

    doktor_adi = request.form.get(
        "doktor_adi", ""
    ).strip()

    brans = request.form.get(
        "brans", ""
    ).strip()

    telefon_girisi = request.form.get(
        "telefon", ""
    ).strip()

    email = request.form.get(
        "email", ""
    ).strip().lower()

    sifre = request.form.get(
        "sifre", ""
    ).strip()

    calisma_saatleri = request.form.get(
        "calisma_saatleri", ""
    ).strip()

    durum = request.form.get(
        "durum", "Aktif"
    ).strip()

    telefon_rakamlar = re.sub(
        r"\D",
        "",
        telefon_girisi
    )

    if (
        not doktor_adi
        or not brans
        or not telefon_girisi
        or not email
        or not sifre
        or not calisma_saatleri
    ):
        flash(
            "Doktor eklemek için tüm alanları doldurunuz.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    if len(telefon_rakamlar) not in [10, 11]:
        flash(
            "Telefon numarası 10 veya 11 haneli olmalıdır.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    if not email_gecerli_mi(email):
        flash(
            "Geçerli bir e-posta adresi giriniz.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    if not sifre_kurallarina_uygun_mu(sifre):
        flash(
            "Şifre en az 8 karakter olmalı; "
            "büyük harf, küçük harf, rakam ve sembol içermelidir.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    if not calisma_saatleri_gecerli_mi(
        calisma_saatleri
    ):
        flash(
            "Çalışma saatlerini 09:00 - 17:00 "
            "biçiminde giriniz. Başlangıç saati "
            "bitiş saatinden önce olmalıdır.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    izinli_branslar = [
        "Dahiliye",
        "Kardiyoloji",
        "Göz Hastalıkları",
        "Ortopedi",
        "Dermatoloji"
    ]

    if brans not in izinli_branslar:
        flash(
            "Geçerli bir branş seçiniz.",
            "hata"
        )

        return redirect(
            url_for(
                "admin_panel",
                bolum="doktor-yonetimi"
            )
        )

    if durum not in ["Aktif", "Pasif"]:
        durum = "Aktif"

    doktor_adi = doktor_adi_duzenle(
        doktor_adi
    )

    veritabani_durum = (
        "aktif"
        if durum == "Aktif"
        else "pasif"
    )

    baglanti = baglanti_olustur()
    imlec = baglanti.cursor()

    try:
        mevcut_email = imlec.execute("""
            SELECT id
            FROM kullanicilar
            WHERE LOWER(email) = LOWER(?)
        """, (email,)).fetchone()

        if mevcut_email:
            flash(
                "Bu e-posta adresi ile kayıtlı kullanıcı zaten var.",
                "hata"
            )

            return redirect(
                url_for(
                    "admin_panel",
                    bolum="doktor-yonetimi"
                )
            )

        mevcut_doktor = imlec.execute("""
            SELECT id
            FROM doktorlar
            WHERE LOWER(doktor_adi) = LOWER(?)
        """, (doktor_adi,)).fetchone()

        if mevcut_doktor:
            flash(
                "Bu doktor adıyla kayıtlı bir doktor zaten var.",
                "hata"
            )

            return redirect(
                url_for(
                    "admin_panel",
                    bolum="doktor-yonetimi"
                )
            )

        doktor_ad_soyad = (
            doktor_adi
            .replace("Dr. ", "", 1)
            .strip()
        )

        ad_soyad_parcalari = doktor_ad_soyad.split()

        if ad_soyad_parcalari:
            ad = ad_soyad_parcalari[0]

            soyad = " ".join(
                ad_soyad_parcalari[1:]
            )
        else:
            ad = "Doktor"
            soyad = ""

        imlec.execute("""
            INSERT INTO kullanicilar
            (
                tc_no,
                ad,
                soyad,
                dogum_tarihi,
                email,
                telefon,
                sifre,
                rol,
                durum
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            None,
            ad,
            soyad,
            None,
            email,
            telefon_formatla(telefon_rakamlar),
            generate_password_hash(sifre),
            "doktor",
            veritabani_durum
        ))

        yeni_kullanici_id = imlec.lastrowid

        imlec.execute("""
            INSERT INTO doktorlar
            (
                kullanici_id,
                doktor_adi,
                poliklinik,
                calisma_saatleri,
                durum
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            yeni_kullanici_id,
            doktor_adi,
            brans,
            calisma_saatleri,
            veritabani_durum
        ))

        baglanti.commit()

        flash(
            f"{doktor_adi} başarıyla eklendi.",
            "basari"
        )

    except sqlite3.IntegrityError:
        baglanti.rollback()

        flash(
            "Doktor kaydedilemedi. "
            "E-posta adresi zaten kullanılıyor olabilir.",
            "hata"
        )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Doktor ekleme sırasında hata oluştu."
        )

        flash(
            "Doktor eklenirken beklenmeyen bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    return redirect(
        url_for(
            "admin_panel",
            bolum="doktor-yonetimi"
        )
    )

@app.route(
    "/admin-randevu-iptal/<int:randevu_id>",
    methods=["POST"]
)
def admin_randevu_iptal(randevu_id):
    if not giris_kontrol("yonetici"):
        return redirect(url_for("giris"))

    baglanti = baglanti_olustur()

    bosalan_randevu = None

    try:
        randevu = baglanti.execute("""
            SELECT
                id,
                doktor_id,
                poliklinik,
                tarih,
                saat,
                durum
            FROM randevular
            WHERE id = ?
        """, (
            randevu_id,
        )).fetchone()

        if not randevu:
            flash(
                "İptal edilecek randevu bulunamadı.",
                "hata"
            )

        elif randevu["durum"] == "iptal_edildi":
            flash(
                "Bu randevu zaten iptal edilmiş.",
                "hata"
            )

        else:
            baglanti.execute("""
                UPDATE randevular
                SET durum = 'iptal_edildi'
                WHERE id = ?
            """, (
                randevu_id,
            ))

            baglanti.commit()

            bosalan_randevu = {
                "doktor_id": randevu["doktor_id"],
                "poliklinik": randevu["poliklinik"],
                "tarih": randevu["tarih"],
                "saat": randevu["saat"]
            }

            flash(
                "Randevu yönetici tarafından iptal edildi.",
                "basari"
            )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Admin randevu iptal işlemi sırasında "
            "hata oluştu."
        )

        flash(
            "Randevu iptal edilirken bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    if bosalan_randevu:

        sonuc = bosalan_randevu_bildirimlerini_gonder(
            bosalan_randevu["doktor_id"],
            bosalan_randevu["poliklinik"],
            bosalan_randevu["tarih"],
            bosalan_randevu["saat"]
        )

        if sonuc["gonderilen"] > 0:
            flash(
                f"Bekleme listesindeki "
                f"{sonuc['gonderilen']} hastaya "
                f"e-posta bildirimi gönderildi.",
                "basari"
            )

        elif sonuc["bekleyen"] > 0:
            flash(
                "Randevu iptal edildi ancak "
                "e-posta bildirimi gönderilemedi. "
                "SMTP ayarlarını kontrol ediniz.",
                "hata"
            )

    return redirect(
        url_for(
            "admin_panel",
            bolum="randevu-yonetimi"
        )
    )

@app.route(
    "/admin-bekleme-kayit-kaldir/<int:kayit_id>",
    methods=["POST"]
)
def admin_bekleme_kayit_kaldir(kayit_id):
    if not giris_kontrol("yonetici"):
        return redirect(url_for("giris"))

    baglanti = baglanti_olustur()

    try:
        kayit = baglanti.execute("""
            SELECT
                id,
                durum
            FROM bekleme_listesi
            WHERE id = ?
        """, (kayit_id,)).fetchone()

        if not kayit:
            flash(
                "Bekleme listesi kaydı bulunamadı.",
                "hata"
            )

        elif kayit["durum"] != "beklemede":
            flash(
                "Bu bekleme listesi kaydı zaten kaldırılmış.",
                "hata"
            )

        else:
            baglanti.execute("""
                UPDATE bekleme_listesi
                SET durum = ?
                WHERE id = ?
            """, (
                "listeden_cikildi",
                kayit_id
            ))

            baglanti.commit()

            flash(
                "Bekleme listesi kaydı kaldırıldı.",
                "basari"
            )

    except Exception:
        baglanti.rollback()

        app.logger.exception(
            "Admin bekleme kaydı kaldırırken hata oluştu."
        )

        flash(
            "Bekleme listesi kaydı kaldırılırken "
            "bir hata oluştu.",
            "hata"
        )

    finally:
        baglanti.close()

    return redirect(
        url_for(
            "admin_panel",
            bolum="bekleme-listesi"
        )
    )

@app.route("/cikis")
def cikis():
    session.clear()
    return redirect(url_for("giris"))

if __name__ == "__main__":
    app.run(debug=False)