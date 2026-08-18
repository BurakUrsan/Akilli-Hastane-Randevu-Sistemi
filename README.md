# Akıllı Hastane Randevu Sistemi

Akıllı Hastane Randevu Sistemi, hastaların çevrim içi olarak randevu oluşturabilmesi, doktorların randevularını takip edebilmesi ve yöneticilerin hasta, doktor ve randevu işlemlerini yönetebilmesi amacıyla geliştirilmiş web tabanlı bir hastane randevu uygulamasıdır.

Bu proje bilgisayar mühendisliği staj çalışması kapsamında Python, Flask ve SQLite kullanılarak geliştirilmiştir.

---

## Kullanılan Teknolojiler

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript
- SMTP / Gmail
- Werkzeug
- python-dotenv

---

## Sistem Özellikleri

### Hasta İşlemleri

- Hasta kayıt olma
- Hasta giriş yapma
- Profil bilgilerini görüntüleme ve güncelleme
- Şifre değiştirme
- Poliklinik ve doktor seçerek randevu oluşturma
- Doktorun çalışma saatlerine göre uygun randevu saatlerini görüntüleme
- Dolu randevu saatlerini görüntüleme
- Randevu iptal etme
- Dolu randevu için bekleme listesine katılma
- Bekleme listesinden çıkma
- Boşalan randevu için e-posta bildirimi alma
- Poliklinik yoğunluk bilgilerini görüntüleme
- Şifremi unuttum özelliğini kullanma
- E-posta üzerinden güvenli şifre sıfırlama

### Doktor İşlemleri

- Doktor hesabı ile giriş yapma
- Doktora ait randevuları görüntüleme
- Hasta bilgilerini görüntüleme
- Randevu notlarını yönetme
- Profil bilgilerini güncelleme
- Çalışma saatlerini güncelleme
- Şifre değiştirme

### Yönetici İşlemleri

- Yönetici hesabı ile giriş yapma
- Hasta listesini görüntüleme
- Doktor listesini görüntüleme
- Sisteme yeni doktor ekleme
- Hasta adına randevu oluşturma
- Randevuları görüntüleme
- Randevu iptal etme
- Bekleme listelerini görüntüleme
- Poliklinik yoğunluk bilgilerini görüntüleme

---

## Bekleme Listesi Sistemi

Bir randevu saati dolu olduğunda hasta aynı doktor, tarih ve saat için bekleme listesine katılabilir.

Randevu iptal edildiğinde sistem aynı randevuyu bekleyen hastaları veritabanından tespit eder.

Bekleme listesinde bulunan uygun hastalara otomatik olarak e-posta bildirimi gönderilir.

Gönderilen e-posta hastaya otomatik olarak randevu oluşturmaz.

Boşalan randevuyu sistem üzerinden işlemi ilk tamamlayan hasta alır.

Aynı doktor, tarih ve saat için yalnızca bir aktif randevu bulunmasına izin verilir.

---

## E-posta Bildirim Sistemi

E-posta işlemleri SMTP üzerinden gerçekleştirilmektedir.

Sistem aşağıdaki durumlarda e-posta gönderebilir:

- Bekleme listesindeki randevu saatinin boşalması
- Şifre sıfırlama isteği

E-posta gönderimlerinin sonuçları veritabanındaki bildirim kayıtlarında tutulmaktadır.

Bildirim durumları:

```text
gonderildi
basarisiz
gonderilmedi
```

şeklinde takip edilmektedir.

E-posta gönderiminde hata meydana gelmesi, başarılı şekilde gerçekleştirilen randevu iptal işlemini geri almaz.

---

## Şifre Güvenliği

Kullanıcı şifreleri veritabanında düz metin olarak saklanmamaktadır.

Şifreler Werkzeug güvenlik fonksiyonları kullanılarak hashlenmiş şekilde saklanmaktadır.

Bu nedenle veritabanında gerçek kullanıcı şifreleri yerine aşağıdakine benzer hash değerleri bulunur:

```text
scrypt:...
```

Giriş sırasında kullanıcının yazdığı şifre, veritabanındaki hash değeri ile güvenli şekilde karşılaştırılır.

---

## Şifre Sıfırlama Sistemi

Kullanıcı giriş ekranındaki "Şifremi Unuttum" özelliğini kullanarak e-posta adresi üzerinden yeni şifre oluşturabilir.

Şifre sıfırlama işlemi sırasında:

- Güvenli ve rastgele bir token oluşturulur.
- Tokenın kendisi yerine hash değeri veritabanında saklanır.
- Kullanıcıya e-posta üzerinden şifre sıfırlama bağlantısı gönderilir.
- Bağlantı 30 dakika boyunca geçerlidir.
- Bağlantı yalnızca bir kez kullanılabilir.
- Yeni bir sıfırlama isteği oluşturulursa önceki bağlantı geçersiz hale gelir.
- Kullanıcının belirlediği yeni şifre güvenli şekilde hashlenerek kaydedilir.

Sistemde kayıtlı olmayan e-posta adresleri için kullanıcı bilgilerinin dışarıya verilmesini engellemek amacıyla genel bir bilgilendirme mesajı gösterilir.

---

# Kurulum

## 1. Python

Projeyi çalıştırabilmek için bilgisayarda Python kurulu olmalıdır.

Python kurulumunun kontrolü için:

```powershell
python --version
```

komutu kullanılabilir.

---

## 2. Sanal Ortam Oluşturma

Proje klasöründe terminal açılarak aşağıdaki komut çalıştırılır:

```powershell
python -m venv venv
```

Windows PowerShell üzerinde sanal ortamı etkinleştirmek için:

```powershell
.\venv\Scripts\Activate.ps1
```

Sanal ortam başarıyla etkinleştirildiğinde terminal satırının başında genellikle:

```text
(venv)
```

ifadesi görünür.

---

## 3. Gerekli Paketlerin Kurulması

Sanal ortam etkinleştirildikten sonra:

```powershell
pip install -r requirements.txt
```

komutu çalıştırılır.

Bu işlem uygulamanın ihtiyaç duyduğu Python paketlerini yükler.

---

## 4. Ortam Değişkenlerinin Ayarlanması

Proje içerisinde güvenlik nedeniyle gerçek `.env` dosyası bulunmamaktadır.

Bunun yerine örnek yapı:

```text
.env.example
```

dosyasında gösterilmiştir.

`.env.example` dosyasının bir kopyası oluşturulmalı ve kopyanın adı:

```text
.env
```

olarak değiştirilmelidir.

Son durumda proje klasöründe:

```text
.env.example
.env
```

dosyaları bulunmalıdır.

`.env.example` dosyasındaki örnek yapı:

```env
FLASK_SECRET_KEY=BURAYA_GUVENLI_BIR_ANAHTAR

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=ornek@gmail.com
SMTP_PASSWORD=UYGULAMA_SIFRESI
SMTP_FROM=ornek@gmail.com
SMTP_SECURITY=ssl
```

şeklindedir.

---

## 5. Flask Secret Key Oluşturma

Güvenli bir Flask anahtarı oluşturmak için terminalde:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

komutu çalıştırılabilir.

Oluşturulan değer `.env` dosyasındaki:

```env
FLASK_SECRET_KEY=
```

alanına yazılmalıdır.

Örnek:

```env
FLASK_SECRET_KEY=OLUSTURULAN_GUVENLI_DEGER
```

Bu değer gizli tutulmalıdır.

---

## 6. Gmail / SMTP Ayarları

E-posta bildirimlerinin kullanılabilmesi için `.env` içerisinde geçerli SMTP bilgileri tanımlanmalıdır.

Gmail kullanılması durumunda:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SECURITY=ssl
```

kullanılabilir.

`SMTP_USER` ve `SMTP_FROM` alanlarına e-posta adresi yazılır.

```env
SMTP_USER=ornek@gmail.com
SMTP_FROM=ornek@gmail.com
```

`SMTP_PASSWORD` alanında normal Gmail hesap şifresi yerine Google tarafından oluşturulan Uygulama Şifresi kullanılmalıdır.

Örnek:

```env
SMTP_PASSWORD=UYGULAMA_SIFRESI
```

Gerçek uygulama şifresi kaynak kod içerisine veya `.env.example` dosyasına yazılmamalıdır.

---

# Uygulamanın Çalıştırılması

Gerekli paketler ve `.env` ayarları tamamlandıktan sonra proje klasöründe:

```powershell
python app.py
```

komutu çalıştırılır.

Uygulama çalıştıktan sonra tarayıcı üzerinden:

```text
http://127.0.0.1:5000
```

adresine gidilebilir.

---

# Veritabanı

Projede SQLite veritabanı kullanılmaktadır.

Uygulama ilk kez çalıştırıldığında gerekli veritabanı tabloları otomatik olarak oluşturulur.

Temel tablolar:

```text
kullanicilar
doktorlar
randevular
bekleme_listesi
bildirimler
sifre_sifirlama
```

tablolarıdır.

Veritabanı ilişkilerinde foreign key desteği kullanılmaktadır.

Aynı doktor, tarih ve saat için birden fazla aktif randevu oluşturulmasını engelleyen veritabanı kontrolleri bulunmaktadır.

---

# Temel Güvenlik Önlemleri

Projede aşağıdaki güvenlik kontrolleri uygulanmıştır:

- Kullanıcı şifrelerinin hashlenerek saklanması
- Flask gizli anahtarının ortam değişkeninden alınması
- SMTP bilgilerinin kaynak kod dışında tutulması
- Şifre sıfırlama tokenlarının hashlenerek saklanması
- Süreli ve tek kullanımlık şifre sıfırlama bağlantıları
- Pasif kullanıcıların sisteme girişinin engellenmesi
- Pasif doktorlara randevu oluşturulmasının engellenmesi
- Geçmiş tarih ve saate randevu oluşturulmasının engellenmesi
- Doktor çalışma saatleri dışında randevu oluşturulmasının engellenmesi
- Aynı randevu saatinin birden fazla hastaya verilmesinin engellenmesi
- E-posta ve kullanıcı girişlerinin backend tarafında doğrulanması
- SMTP bağlantısında SSL veya STARTTLS kullanılması
- Flask debug modunun final sürümünde kapalı tutulması

---

# Not

E-posta bildirim sisteminin çalışabilmesi için projeyi çalıştıracak kişinin kendi geçerli SMTP bilgilerini `.env` dosyasına tanımlaması gerekmektedir.

SMTP bilgileri tanımlanmadığında e-posta gerektirmeyen temel sistem özellikleri kullanılabilir ancak e-posta bildirimleri gerçekleştirilemez.

---

# Geliştirici

**Burak Urşan**

Nevşehir Hacı Bektaş Veli Üniversitesi  
Bilgisayar Mühendisliği

Akıllı Hastane Randevu Sistemi, bilgisayar mühendisliği staj çalışması kapsamında geliştirilmiştir.