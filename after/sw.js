// 최소 서비스워커: 설치 가능(PWA) 요건 충족용.
// 데이터는 항상 네트워크에서 가져온다 (캐시로 인한 구버전 표시 방지).
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });
self.addEventListener('fetch', function (e) { /* network passthrough */ });
