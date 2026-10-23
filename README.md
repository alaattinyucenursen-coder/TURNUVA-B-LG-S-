# Satranç Turnuvaları

TSF (Türkiye Satranç Federasyonu) turnuvalarını tek bir yerde toplayan uygulama.

- Turnuva listesi: tarih, il, kategoriler, ödüller
- Filtreler: il, tür, kategori, arama
- Eşleşme ve sonuçlar için chess-results.com sayfalarına bağlantı
- Biten turnuvalar listeden otomatik düşer

## Çalıştırma

`web/` klasörü statik bir web uygulamasıdır. Yerelde denemek için:

```
cd web && python3 -m http.server 8000
```

Sonra tarayıcıda http://localhost:8000 adresini aç.

Turnuva verisi `web/tournaments.json` dosyasındadır (şimdilik örnek veri).
