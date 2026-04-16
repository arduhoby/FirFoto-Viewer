# FirFoto Viewer Revize Plan

Bu doküman, mevcut `Firfoto` prototipinden `FirFoto Viewer` adlı yeni, Flutter tabanlı, çok platformlu masaüstü uygulamaya geçiş planını tanımlar.

Bu sürümde amaç sadece yeni hedefi yazmak değil, aynı zamanda:

- şimdiye kadar ne yaptığımızı kaybetmemek
- hangi parçaların korunacağını netleştirmek
- hangi parçaların geçici olduğunu işaretlemek
- hangi parçaların artık kullanılmayacağını açıkça belirtmek

Bu belge tartışma ve karar dokümanıdır. Uygulama geçişi bunun üzerinden netleştirilecektir.

---

## 1. Yeni Ürün Adı ve Yön

- Yeni ürün adı: `FirFoto Viewer`
- Yeni ana teknoloji yönü: `Flutter Desktop`
- Hedef platformlar:
  - `macOS`
  - `Windows`
  - `Linux`

Ana karar:

- Bundan sonra proje, bir `Flutter çok platformlu masaüstü uygulaması` olarak devam edecek.
- Mevcut Python tabanlı yapı tamamen çöpe atılmayacak.
- Python tarafı, geçiş sürecinde çekirdek analiz ve metadata/SQLite referansı olarak değerlendirilecek.
- Kalıcı hedefte UI tarafı Flutter olacak.

---

## 2. Proje Özeti

`FirFoto Viewer`, amatör ve profesyonel fotoğrafçıların çok sayıda çekilmiş kareyi bir arada görmesini, ön seçime sokmasını, teknik sorunları erkenden fark etmesini ve bu kararları kalıcı olarak saklamasını sağlayan bir desktop uygulaması olacaktır.

Temel kullanım amacı:

- aynı çekimdeki çok sayıdaki fotoğrafı hızlıca birlikte görmek
- ön seçim yapmak
- makinenin netleme noktalarıyla birlikte objenin flu olup olmadığını değerlendirmek
- ışık yetersizliğini ve bunun düzeltilebilir olup olmadığını önceden raporlamak
- etiketleme yapmak
- kategori tahmini yapmak
- kullanıcı düzeltirse aynı klasör veya istenirse diğer klasörler için yeniden değerlendirme yapmak

İlk pratik hedef:

- hızlı klasör açma
- hızlı dosya listesi
- hızlı thumbnail strip
- büyük preview
- EXIF/metadata paneli
- kamera/lens/çekim verisi doğruluğu
- etiketleme sistemi
- makine AF noktası ve tahmini sharp ayrımı
- ışık yetersizliği / kurtarılabilirlik ön raporu
- SQLite’dan sonuç yükleme
- sonra analiz entegrasyonu

Yani yeni öncelik:

1. hızlı görüntüleme
2. doğru metadata ve kamera bilgisi
3. ön seçim ve etiketleme
4. kalıcı sonuçlar
5. sonra gelişmiş analiz

---

## 3. Varsayımlar

- İlk hedef performans problemi yaşayan mevcut Qt GUI’yi büyütmek değil, Flutter tabanlı daha temiz bir UI katmanı kurmaktır.
- Apple Silicon performansı bizim için önemlidir, ama çözüm sadece işlemci gücü değil, doğru mimari olacaktır.
- Mevcut Python analiz motoru ilk geçişte tamamen atılmayabilir.
- Mevcut SQLite şeması, geçişte referans veya ara katman olarak kullanılabilir.
- NEF/Nikon odaklı örnek veri elimizde olduğu için ilk doğrulama Nikon dosyalarıyla yapılacaktır.
- AF overlay ve sharp guess aynı şey değildir; yeni üründe bunlar kesin olarak ayrı katmanlar olarak ele alınacaktır.
- Kullanıcı etiket listesi uygulama tarafından yönetilecek ve varsayılan etiket seti ile başlayacaktır.
- Kategori tahmini kullanıcı tarafından düzeltilebilecek ve bu düzeltme tekrar değerlendirme akışını tetikleyebilecektir.

---

## 4. Mimari Öneri

Yeni yapı 4 ana katmandan oluşmalı:

### 4.1 UI Katmanı

- Flutter desktop UI
- liste
- thumbnail strip
- preview alanı
- metadata paneli
- filtreleme ve seçim akışı

### 4.2 Uygulama Katmanı

- state yönetimi
- seçili klasör
- seçili dosya
- etiket listeleri
- kullanıcı tercihleri
- yeniden değerlendirme kuyruğu
- thumbnail cache
- preview cache
- arka plan görevleri
- progress/cancel

### 4.3 Veri Katmanı

- SQLite
- kamera veritabanı
- klasör bazlı analiz geçmişi
- dosya bazlı sonuçlar
- kategori
- kullanıcı etiketi
- karar
- nedenler
- metadata snapshot
- yeniden değerlendirme durumu

### 4.4 Analiz Katmanı

Geçici aşama:

- Python çekirdeği kullanılabilir

Sonraki aşama:

- bazı parçalar Dart
- bazı parçalar native plugin
- bazı parçalar servis şeklinde olabilir
- kategori tahmini
- ışık düzeltilebilirlik raporu
- obje flu / focus subject kontrolü

---

## 5. Mevcut Yapının Durumu

Bu bölüm önemli. Elimizdeki parçaları 4 sınıfa ayırıyoruz:

- `Korunacak`
- `Geçişte kullanılacak`
- `Referans olarak tutulacak`
- `Kullanılmayacak / emekli edilecek`

### 5.1 Korunacak Parçalar

Bunlar doğrudan ya da uyarlanarak yaşamaya devam etmeli:

- domain modelleri mantığı
- SQLite kalıcılık mantığı
- metadata okuma mantığı
- Nikon AF/MakerNote araştırması
- test örnekleri ve gerçek dosya doğrulama yaklaşımı
- analiz akışının açıklanabilir olma hedefi

Mevcut dosya referansları:

- `src/firfoto/core/models.py`
- `src/firfoto/storage/sqlite.py`
- `src/firfoto/core/metadata.py`
- `src/firfoto/core/workflow.py`

### 5.2 Geçişte Kullanılacak Parçalar

Bunlar yeni Flutter projeye birebir taşınmayabilir ama geçici köprü olabilir:

- Python CLI analiz akışı
- batch workflow
- mevcut SQLite yazımı
- temel kalite metriği üretimi

Mevcut dosya referansları:

- `src/firfoto/cli.py`
- `src/firfoto/core/analyzer.py`
- `src/firfoto/core/image_metrics.py`
- `src/firfoto/core/workflow.py`

### 5.3 Referans Olarak Tutulacak Parçalar

Bunlar tasarım ve davranış referansı olarak yararlı ama yeni üründe aynı şekilde yaşamayacak:

- mevcut Qt layout fikirleri
- detay paneli yapısı
- mevcut preview akışı
- thumbnail/list senkronuna dair öğrenilen dersler
- progress/cancel akışı

Mevcut dosya referansları:

- `src/firfoto/gui/qt_app.py`
- `src/firfoto/gui/image_loader.py`
- `src/firfoto/gui/formatters.py`

### 5.4 Kullanılmayacak / Emekli Edilecek Parçalar

Bu bölüm özellikle net olmalı:

- `Qt GUI` nihai ürün olmayacak
- `PySide6 masaüstü arayüzü` artık uzun vadeli yön değil
- UI geliştirme bundan sonra Python/Qt üzerinde devam etmeyecek
- Tk tarafı zaten geçiciydi, tamamen emekli kabul edilmeli

Dolayısıyla:

- `src/firfoto/gui/qt_app.py`:
  - aktif kullanımda olabilir
  - ama yeni hedef ürünün kalıcı UI’sı değildir
- Flutter geçişinden sonra bu dosya:
  - ya bakım moduna alınacak
  - ya da yalnızca eski prototip referansı olarak tutulacak

---

## 6. Neden Flutter?

Flutter seçiminin temel sebepleri:

- çok platform desteği
- modern UI üretim hızı
- masaüstü için daha kontrollü state ve render akışı
- thumbnail/list/preview gibi arayüzlerde daha güçlü ayrıştırma şansı
- gelecekte mobil varyasyon ihtimali doğarsa tekrar kullanım potansiyeli

Ama dikkat:

- Flutter tek başına sihirli performans çözümü değildir
- ağır işleri UI thread’e koyarsak yine yavaşlar
- özellikle RAW decode, metadata parse ve thumbnail üretimi arka plan iş akışında olmalıdır

Yani yeni kural:

- Flutter UI
- ağır iş background isolate / worker / native layer

---

## 7. Yeni Ürün İlkeleri

`FirFoto Viewer` için kesin ürün ilkeleri:

- non-destructive
- silme yok
- overwrite yok
- kullanıcı onayı olmadan taşıma/kopyalama yok
- kararlar açıklanabilir
- AF alanı ile sharp guess ayrı
- metadata ile tahmin edilen bilgi karıştırılmayacak
- makineden gelen netleme alanı ile uygulama tahmini ayrı katmanlar olacak
- etiketler kullanıcı tarafından düzenlenebilir olacak
- varsayılan etiket listesi ürünle birlikte gelecek
- kategori tahmini kullanıcı düzeltmesiyle yeniden öğrenme/revizyon akışına girebilecek
- ışık yetersizliği ve kurtarılabilirlik ayrı raporlanacak
- browse hızlı olacak
- load ile analyze ayrı akışlar olacak
- dosya seçimi UI’yi bloklamayacak

---

## 8. Hedef Kullanıcılar ve Kullanım Senaryosu

### 8.1 Hedef Kullanıcılar

- profesyonel fotoğrafçılar
- ileri seviye amatör fotoğrafçılar
- kuş / wildlife fotoğrafçıları
- portre çalışan kullanıcılar
- çok sayıda seri çekim yapan kullanıcılar

### 8.2 Ana Kullanım Senaryosu

- kullanıcı klasör açar
- tüm çekilen fotoğrafları birlikte görür
- hızlı ön seçime başlar
- makinenin netleme alanını isterse açar
- tahmini sharp alanını isterse ayrıca açar
- objenin flu olup olmadığına bakar
- teknik sorunları görür
- etiketler ekler
- kategori tahminini düzeltirse sistem yeniden değerlendirir

---

## 9. Revize Aşamalı Yol Haritası

### Aşama 0: Geçiş Mimarisi ve Proje Yeniden Adlandırma

#### Amaç

- `FirFotoViewer` kimliğini ve Flutter yönünü netleştirmek

#### Yapılacaklar

- yeni ürün adı ve klasör yapısı kararı
- mevcut Python yapının hangi rolü üstleneceğini netleştirmek
- Flutter uygulama iskeleti için karar dokümanı

#### Çıktılar

- revize mimari
- geçiş sınırları
- modül sorumlulukları

#### Riskler

- hem Qt hem Flutter’ı aynı anda büyütmeye çalışmak

#### Test Planı

- yok, bu planlama aşaması

#### Teslim Kriteri

- geçiş yolu net olmalı

---

### Aşama 1: Flutter Desktop İskeleti

#### Amaç

- çok platformlu Flutter masaüstü projesini başlatmak

#### Yapılacaklar

- Flutter desktop scaffold
- temel klasör yapısı
- state yönetimi seçimi
- app shell
- ana pencere iskeleti

#### Çıktılar

- çalışan Flutter desktop app

#### Riskler

- yanlış state mimarisi

#### Test Planı

- launch test
- widget smoke test

#### Teslim Kriteri

- uygulama açılıyor olmalı

---

### Aşama 2: Browse, Load, Analyze Akışının Ayrılması

#### Amaç

- mevcut en kritik UX hatasını kalıcı olarak çözmek

#### Yapılacaklar

- `Browse`
  - sadece klasör seçer
- `Load`
  - dosya listesi, thumbnail, preview hazırlığı
- `Analyze`
  - gerçek analiz çalıştırır

#### Çıktılar

- hızlı browse
- kontrollü load
- ayrı analyze

#### Riskler

- kullanıcı akışını fazla karmaşıklaştırmak

#### Test Planı

- browse latency testi
- load sonrası liste testi
- analyze sonrası sonuç testi

#### Teslim Kriteri

- kullanıcı klasör seçince UI blok olmamalı

---

### Aşama 3: Hızlı Dosya Tarayıcı

#### Amaç

- liste, thumbnail strip ve preview’ü gerçekten akıcı hale getirmek

#### Yapılacaklar

- solda dosya listesi
- üst/yan thumbnail strip
- seçili dosya preview
- liste ve thumbnail birebir senkron
- küçük thumbnail cache
- lazy load

#### Çıktılar

- hızlı photo browser

#### Riskler

- büyük klasörlerde bellek tüketimi

#### Test Planı

- 100 / 1000 / 5000 dosya testleri
- scroll ve selection latency ölçümü

#### Teslim Kriteri

- seçim anında belirgin donma olmamalı

---

### Aşama 4: Metadata, Kamera Veritabanı ve EXIF Paneli

#### Amaç

- makine, lens, odak uzaklığı, f değeri, enstantane, ISO, AF alanı gibi bilgileri doğru göstermek
- metadata’yı kamera veritabanı ile desteklemek

#### Yapılacaklar

- metadata servis katmanı
- kamera veritabanı modeli
- gövde/lens profili eşleme
- preview ile paralel metadata yükleme
- AF alanı
- sharp guess
- bunların açık ayrımı

#### Çıktılar

- doğru ve açıklanmış bilgi paneli

#### Riskler

- MakerNote uyumsuzlukları
- marka/model varyasyonları

#### Test Planı

- gerçek Nikon NEF örnekleriyle karşılaştırma
- kamera veri tabanı eşleme doğrulaması

#### Teslim Kriteri

- metadata, kamera ekranı ile makul düzeyde tutarlı olmalı

---

### Aşama 5: Etiketleme, Kategori ve SQLite Kalıcılığı

#### Amaç

- analizlerin, kararların, etiketlerin ve metadata snapshot’larının kalıcı olması

#### Yapılacaklar

- Flutter SQLite erişim katmanı
- klasör bazlı kayıt
- son analizlerin geri yüklenmesi
- varsayılan etiket listesi
- kullanıcı etiket listesi yönetimi
- kategori tahmini saklama
- kullanıcı kategori düzeltmesi saklama
- tekrar değerlendirme işaretleme
- ileride filtreleme/sıralama desteği

#### Çıktılar

- kalıcı sonuç altyapısı
- kalıcı etiket altyapısı

#### Riskler

- Python ve Flutter arasında şema uyumu
- kullanıcı düzeltmesi sonrası yeniden değerlendirme kuralları

#### Test Planı

- save/load testleri
- aynı klasörü yeniden açma testi
- etiket kaydet/yükle testi
- kategori override testi

#### Teslim Kriteri

- eski analiz geri gelmeli

---

### Aşama 6: Python Analiz Motoru ile Geçiş Köprüsü

#### Amaç

- Flutter UI’dan mevcut analizi kullanabilmek

#### Yapılacaklar

- Python CLI çağırma veya servis katmanı
- progress
- cancel
- sonuç dönüşü

#### Çıktılar

- Flutter içinden analiz başlatma

#### Riskler

- süreç yönetimi

#### Test Planı

- analyze/cancel akışı

#### Teslim Kriteri

- Flutter’dan gerçek analiz tetiklenmeli

---

### Aşama 7: Performans Sertleştirme

#### Amaç

- Apple Silicon başta olmak üzere tüm platformlarda akıcı deneyim

#### Yapılacaklar

- isolate/worker yapısı
- preview cache
- metadata cache
- thumbnail cache
- seçili dosya öncelikli yükleme
- gereksiz yeniden decode işlerini kaldırma

#### Çıktılar

- akıcı seçim ve gezinme

#### Riskler

- karmaşık cache invalidation

#### Test Planı

- gerçek büyük klasör performans ölçümü
- frame drop ve input latency gözlemi

#### Teslim Kriteri

- seçim anında bekleme hissi minimum olmalı

---

### Aşama 8: Gelişmiş Analiz, Kategori Tahmini ve Teknik Uyarılar

#### Amaç

- gerçek ürün zekasını eklemek

#### Yapılacaklar

- kategori tahmini
- kullanıcı düzeltmesine göre yeniden değerlendirme
- subject-aware sharpness
- netleme yapılan objenin flu olup olmadığını ölçme
- burst comparison
- ışık yetersizliği analizi
- ışığın ne kadar düzeltilebilir olduğuna dair ön rapor
- reasoning paneli

#### Çıktılar

- daha güçlü culling sistemi
- açıklanabilir ön seçim sistemi

#### Riskler

- açıklanabilirliği kaybetmek

#### Test Planı

- örnek dataset bazlı kıyas
- kullanıcı override sonrası tekrar değerlendirme testi

#### Teslim Kriteri

- neden seçildi / neden elendi açıkça görülebilmeli

---

## 10. MVP Kapsamı

Flutter tabanlı ilk gerçek MVP için önerilen kapsam:

- Browse
- Load
- Analyze ayrı düğme olarak tasarlanacak, ama ilk viewer MVP'sinde analiz ikinci öncelik olacak
- dosya listesi
- tüm dosyalar için thumbnail strip
- büyük preview
- modern ve güçlü görsel sunum
- klavye ile gezinme:
  - `Sağ ok`: sonraki dosya
  - `Sol ok`: önceki dosya
  - `Yukarı ok`: büyüt
  - `Aşağı ok`: küçült
- mouse / trackpad ile doğal kullanım:
  - scroll / iki parmak hareketi ile gezinme
  - mouse ile sol tık seçimi
- EXIF temel bilgiler
- AF alanı gösterimi
- tahmini sharp gösterimi
- varsayılan etiket listesi
- kullanıcı etiket seçimi
- temel kategori tahmini
- kategori override
- SQLite kalıcılığı
- sonuç geri yükleme

Bu aşamada şart olmayanlar:

- dosya taşıma/kopyalama
- burst karar motoru
- AI kategori tahmini
- subject detection
- gelişmiş analiz motoru
- kategori yeniden değerlendirme otomasyonu

---

## 11. MVP Sonrası Genişleme

- kategori tahmini
- subject-aware blur analizi
- ışık kurtarılabilirlik modeli
- burst group comparison
- selected/rejected yönetimi
- taşıma/kopyalama workflow
- AI destekli kalite kararları
- DMG/app dağıtımı

---

## 12. Şu Ana Kadarki Öğrenimler

Bu kısmı özellikle korumak istiyorum, çünkü geçişte çok işimize yarayacak:

- browse ile load aynı şey değil
- analyze ile preview aynı şey değil
- AF noktası ile sharp guess aynı şey değil
- kullanıcı override ettiği kategori kaybolmamalı
- etiketleme sadece dosya işareti değil, analiz akışının parçası olmalı
- seçim olayında RAW decode yapmak UI’yi öldürüyor
- thumbnail strip’i her seçimde baştan kurmak büyük hata
- metadata tekrar tekrar okunursa seçim akışı bozuluyor
- kalıcı SQLite sonuçları çok yararlı

Bu öğrenimler yeni Flutter mimarisinin temel kuralı olmalı.

---

## 13. Açık Kararlar

Tartışmamız gereken net noktalar:

1. Yeni Flutter proje klasörü mevcut repo içinde mi olacak?
2. Mevcut Python kodu aynı repo içinde `backend/core` gibi mi kalacak?
3. İlk Flutter sürümünde:
   - sadece görüntüleyici mi yapalım
   - yoksa SQLite + analiz entegrasyonunu da aynı turda mı alalım?
4. Varsayılan etiket listesi ilk sürümde hangi set ile gelsin?
5. Kamera veritabanı gövde/lens düzeyinde mi başlasın, yoksa önce yalnızca gövde profiliyle mi?
6. Kategori override sonrası yeniden değerlendirme:
   - sadece aktif klasör mü
   - yoksa kullanıcı onayıyla diğer klasörler de mi?
7. State yönetimi için ne seçelim?
   - Riverpod
   - Bloc
   - Provider
   - başka bir minimal yapı
8. Preview/thumbnail tarafında:
   - ilk aşamada Python köprüsü mü
   - yoksa Flutter/native çözüm mü

---

## 14. Benim Net Önerim

En sağlıklı başlangıç şu:

### Önerilen yeni sıra

1. `FirFotoViewer` adıyla Flutter desktop proje iskeleti
2. `Browse / Load / Analyze` ayrımı
3. modern ve hızlı file browser
4. güçlü preview deneyimi
5. metadata paneli
6. SQLite yükleme
7. Python analiz köprüsü

Yani ilk Flutter turunda:

- tam analiz zekası değil
- önce hızlı, modern ve doğru görüntüleyici
- klavye ve trackpad kullanımı birinci sınıf olmalı

Bu bence en doğru yol.

### Neden `Load` ve `Analyze` ayrı olmalı?

Benim önerim: `Load` ve `Analyze` ayrı kalsın.

Sebep:

- kullanıcı bazen sadece klasörü görmek ister
- büyük klasörlerde analiz pahalıdır
- hızlı viewer deneyimi ile analiz deneyimi aynı iş değildir
- bu ayrım performans sorunlarını azaltır
- kullanıcıya daha öngörülebilir bir akış verir

Önerilen ilk akış:

- `Browse`: klasör seç
- `Load`: dosyaları, listeyi, thumbnail'leri ve preview'ü yükle
- `Analyze`: istenirse sonra çalıştır

Bu, senin şu an istediğin “önce güzel ve işlevsel viewer” yaklaşımıyla tam uyumlu.

---

## 15. Şimdilik Kullanılmayacaklar

Bu liste özellikle net olsun:

- Qt GUI üzerinde büyük yatırım yapılmayacak
- mevcut Qt performans tuning çalışmaları artık ana yön olmayacak
- Tk tarafı tamamen terk edildi
- Python GUI artık ana ürün yönü değil

Yani bundan sonra masaüstü UI çalışması:

- `Flutter tarafında`

olacak.

---

## 16. Sonuç

Karar:

- ürün adı artık `FirFoto Viewer`
- yön artık `Flutter çok platformlu masaüstü uygulaması`
- mevcut Python yapı:
  - tamamen atılmıyor
  - ama UI tarafında ana yol olmaktan çıkıyor

Bu belge onaylandıktan sonra bir sonraki teknik adım:

- Flutter proje yapısının detay planı
- klasör organizasyonu
- ilk uygulama iskeleti
