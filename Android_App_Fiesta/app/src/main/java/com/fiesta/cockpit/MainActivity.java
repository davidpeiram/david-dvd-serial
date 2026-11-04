package com.fiesta.cockpit;

import android.Manifest;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends Activity {

    private static final String ACTION_USB_PERMISSION = "com.fiesta.cockpit.USB_PERMISSION";
    private static final int PERMISSION_REQ_CODE = 301;

    private WebView webView;
    private UsbManager usbManager;
    private UsbDeviceConnection usbConnection;
    private UsbEndpoint epIn;
    private UsbEndpoint epOut;
    private final AtomicBoolean isConnected = new AtomicBoolean(false);
    private final AtomicBoolean snifferMode = new AtomicBoolean(false);
    private Thread readThread;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private LocationManager locationManager;
    private LocationListener locationListener;
    private final AtomicBoolean isGpsTracking = new AtomicBoolean(false);

    private final Map<String, Long> lastBroadcastSentMs = new ConcurrentHashMap<>();

    private final BroadcastReceiver usbReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (ACTION_USB_PERMISSION.equals(action)) {
                UsbDevice device = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
                if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false) && device != null) {
                    openDevice(device);
                } else {
                    notifyJsStatus("PERMISSION_DENIED", "Permissao USB negada pelo usuario.");
                }
            } else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(action)) {
                scanAndConnectUsb();
            } else if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(action)) {
                closeSerial();
                notifyJsStatus("DISCONNECTED", "Cabo USB desconectado");
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);
        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);

        // Inicia o Foreground Service para evitar congelamento em segundo plano
        startTelemetryForegroundService();

        // Solicita permissões de GPS e Notificação no Android 6 a 14+
        requestAppPermissions();

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(true);
        settings.setAllowUniversalAccessFromFileURLs(true);
        settings.setBlockNetworkImage(false);
        settings.setBlockNetworkLoads(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        if (Build.VERSION.SDK_INT >= 21) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(android.webkit.ConsoleMessage cm) {
                android.util.Log.d("FiestaWebView", cm.message() + " -- Line " + cm.lineNumber() + " of " + cm.sourceId());
                return true;
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                mainHandler.postDelayed(() -> scanAndConnectUsb(), 600);
            }
        });

        webView.addJavascriptInterface(new AndroidUsbBridge(), "AndroidUSB");
        webView.loadUrl("file:///android_asset/index.html");

        setupGpsListener();

        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_USB_PERMISSION);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);

        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(usbReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(usbReceiver, filter);
        }
    }

    private void startTelemetryForegroundService() {
        try {
            Intent sIntent = new Intent(this, TelemetryService.class);
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(sIntent);
            } else {
                startService(sIntent);
            }
        } catch (Exception ignored) {}
    }

    private void requestAppPermissions() {
        if (Build.VERSION.SDK_INT >= 23) {
            List<String> perms = new ArrayList<>();
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                perms.add(Manifest.permission.ACCESS_FINE_LOCATION);
            }
            if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                perms.add(Manifest.permission.ACCESS_COARSE_LOCATION);
            }
            if (Build.VERSION.SDK_INT >= 33) {
                if (checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
                    perms.add("android.permission.POST_NOTIFICATIONS");
                }
            }
            if (!perms.isEmpty()) {
                requestPermissions(perms.toArray(new String[0]), PERMISSION_REQ_CODE);
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQ_CODE) {
            for (int i = 0; i < permissions.length; i++) {
                if (Manifest.permission.ACCESS_FINE_LOCATION.equals(permissions[i])
                        && grantResults.length > i && grantResults[i] == PackageManager.PERMISSION_GRANTED) {
                    if (isGpsTracking.get()) {
                        startGpsInternal();
                    }
                    break;
                }
            }
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.resumeTimers();
        }
    }

    private void setupGpsListener() {
        locationListener = new LocationListener() {
            @Override
            public void onLocationChanged(Location loc) {
                if (loc == null || !isGpsTracking.get()) return;
                double lat = loc.getLatitude();
                double lon = loc.getLongitude();
                double alt = loc.hasAltitude() ? loc.getAltitude() : 0.0;
                float spdKmh = loc.hasSpeed() ? (loc.getSpeed() * 3.6f) : 0.0f;
                float bearing = loc.hasBearing() ? loc.getBearing() : 0.0f;
                float acc = loc.hasAccuracy() ? loc.getAccuracy() : 999.0f;
                dispatchGpsToJs(lat, lon, spdKmh, alt, bearing, acc);
            }

            @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
            @Override public void onProviderEnabled(String provider) {}
            @Override public void onProviderDisabled(String provider) {}
        };
    }

    private synchronized void startGpsInternal() {
        if (locationManager == null || isGpsTracking.get()) return;
        if (Build.VERSION.SDK_INT >= 23) {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, PERMISSION_REQ_CODE);
                return;
            }
        }
        try {
            isGpsTracking.set(true);
            if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locationManager.requestLocationUpdates(
                        LocationManager.GPS_PROVIDER,
                        1000L,
                        0.5f,
                        locationListener,
                        Looper.getMainLooper()
                );
            } else if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locationManager.requestLocationUpdates(
                        LocationManager.NETWORK_PROVIDER,
                        1500L,
                        1.0f,
                        locationListener,
                        Looper.getMainLooper()
                );
            }

            Location lastLoc = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER);
            if (lastLoc == null) {
                lastLoc = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER);
            }
            if (lastLoc != null) {
                dispatchGpsToJs(
                        lastLoc.getLatitude(),
                        lastLoc.getLongitude(),
                        lastLoc.hasSpeed() ? (lastLoc.getSpeed() * 3.6f) : 0.0f,
                        lastLoc.hasAltitude() ? lastLoc.getAltitude() : 0.0,
                        lastLoc.hasBearing() ? lastLoc.getBearing() : 0.0f,
                        lastLoc.hasAccuracy() ? lastLoc.getAccuracy() : 999.0f
                );
            }
            notifyJsGpsStatus(true);
        } catch (Exception ignored) {}
    }

    private synchronized void stopGpsInternal() {
        isGpsTracking.set(false);
        if (locationManager != null && locationListener != null) {
            try {
                locationManager.removeUpdates(locationListener);
            } catch (Exception ignored) {}
        }
        notifyJsGpsStatus(false);
    }

    private void notifyJsGpsStatus(final boolean active) {
        final String js = "if(window.onNativeGpsStatusChanged) window.onNativeGpsStatusChanged(" + active + ");";
        mainHandler.post(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    private void dispatchGpsToJs(double lat, double lon, float speedKmh, double alt, float bearing, float acc) {
        final String js = String.format(
                Locale.US,
                "if(window.onNativeGpsUpdate) window.onNativeGpsUpdate(%.6f, %.6f, %.1f, %.1f, %.1f, %.1f);",
                lat, lon, speedKmh, alt, bearing, acc
        );
        mainHandler.post(() -> {
            if (webView != null) webView.evaluateJavascript(js, null);
        });
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent != null && UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
            scanAndConnectUsb();
        }
    }

    @Override
    protected void onDestroy() {
        stopGpsInternal();
        closeSerial();
        try {
            unregisterReceiver(usbReceiver);
        } catch (Exception ignored) {}
        try {
            stopService(new Intent(this, TelemetryService.class));
        } catch (Exception ignored) {}
        super.onDestroy();
    }

    private synchronized void scanAndConnectUsb() {
        if (isConnected.get()) {
            notifyJsStatus("CONNECTED", "CANable V2.1 Ativa (500 kbps)");
            return;
        }

        if (usbManager == null) {
            notifyJsStatus("ERROR", "UsbManager indisponivel no Android");
            return;
        }

        HashMap<String, UsbDevice> deviceList = usbManager.getDeviceList();
        if (deviceList == null || deviceList.isEmpty()) {
            notifyJsStatus("DISCONNECTED", "Nenhum dispositivo USB detectado no cabo OTG");
            return;
        }

        UsbDevice targetDevice = null;
        for (UsbDevice dev : deviceList.values()) {
            int vid = dev.getVendorId();
            if (vid == 0x16D0 || vid == 0x1D50 || vid == 0x0483) {
                targetDevice = dev;
                break;
            }
        }
        if (targetDevice == null) {
            targetDevice = deviceList.values().iterator().next();
        }

        if (usbManager.hasPermission(targetDevice)) {
            openDevice(targetDevice);
        } else {
            notifyJsStatus("REQUESTING_PERMISSION", "Solicitando permissao USB ao Android...");
            Intent permIntent = new Intent(ACTION_USB_PERMISSION);
            permIntent.setPackage(getPackageName());
            int flags = Build.VERSION.SDK_INT >= 31
                    ? PendingIntent.FLAG_MUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
                    : PendingIntent.FLAG_UPDATE_CURRENT;
            PendingIntent pi = PendingIntent.getBroadcast(this, 0, permIntent, flags);
            usbManager.requestPermission(targetDevice, pi);
        }
    }

    private synchronized void openDevice(UsbDevice device) {
        closeSerial();

        try {
            UsbDeviceConnection conn = usbManager.openDevice(device);
            if (conn == null) {
                notifyJsStatus("ERROR", "Falha ao abrir conexao USB nativa");
                return;
            }

            UsbEndpoint foundIn = null;
            UsbEndpoint foundOut = null;
            int controlInterfaceId = 0;

            // Desanexa o driver CDC do kernel do Android usando force=true nativo!
            for (int i = 0; i < device.getInterfaceCount(); i++) {
                UsbInterface intf = device.getInterface(i);
                conn.claimInterface(intf, true);

                if (intf.getInterfaceClass() == UsbConstants.USB_CLASS_COMM) {
                    controlInterfaceId = intf.getId();
                }

                for (int j = 0; j < intf.getEndpointCount(); j++) {
                    UsbEndpoint ep = intf.getEndpoint(j);
                    if (ep.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK) {
                        if (ep.getDirection() == UsbConstants.USB_DIR_IN) {
                            foundIn = ep;
                        } else if (ep.getDirection() == UsbConstants.USB_DIR_OUT) {
                            foundOut = ep;
                        }
                    }
                }
            }

            if (foundIn == null || foundOut == null) {
                conn.close();
                notifyJsStatus("ERROR", "Endpoints Bulk IN/OUT nao encontrados no dispositivo");
                return;
            }

            // Configura CDC-ACM: SET_LINE_CODING (0x20) -> 115200 bps, 1 stop bit, sem paridade, 8 bits
            int baud = 115200;
            byte[] lineCoding = new byte[] {
                    (byte) (baud & 0xFF),
                    (byte) ((baud >> 8) & 0xFF),
                    (byte) ((baud >> 16) & 0xFF),
                    (byte) ((baud >> 24) & 0xFF),
                    0, // 1 stop bit
                    0, // sem paridade
                    8  // 8 data bits
            };
            conn.controlTransfer(0x21, 0x20, 0, controlInterfaceId, lineCoding, lineCoding.length, 500);

            // SET_CONTROL_LINE_STATE (0x22) -> DTR=1, RTS=1 (0x03)
            conn.controlTransfer(0x21, 0x22, 0x03, controlInterfaceId, null, 0, 500);

            this.usbConnection = conn;
            this.epIn = foundIn;
            this.epOut = foundOut;
            this.isConnected.set(true);

            String devInfo = String.format("CANable %04X:%04X (500k)", device.getVendorId(), device.getProductId());
            notifyJsStatus("CONNECTED", devInfo);

            // Inicializa automaticamente o barramento SLCAN em 500 kbps (Ford HS-CAN)
            new Thread(() -> {
                try {
                    writeRaw("C\r");
                    Thread.sleep(50);
                    writeRaw("S6\r");
                    Thread.sleep(50);
                    writeRaw("O\r");
                    Thread.sleep(50);
                    writeRaw("V\r");
                } catch (Exception ignored) {}
            }).start();

            startReadLoop();

        } catch (Exception e) {
            notifyJsStatus("ERROR", "Erro ao abrir CDC: " + e.getMessage());
            closeSerial();
        }
    }

    private void startReadLoop() {
        readThread = new Thread(() -> {
            byte[] buffer = new byte[512];
            StringBuilder lineBuf = new StringBuilder(128);

            while (isConnected.get() && usbConnection != null && epIn != null) {
                try {
                    int len = usbConnection.bulkTransfer(epIn, buffer, buffer.length, 40);
                    if (len > 0) {
                        for (int i = 0; i < len; i++) {
                            char c = (char) (buffer[i] & 0xFF);
                            if (c == '\r' || c == '\n') {
                                if (lineBuf.length() > 0) {
                                    String line = lineBuf.toString().trim();
                                    lineBuf.setLength(0);
                                    handleIncomingSlcanLine(line);
                                }
                            } else if (c >= 32 && c <= 126) {
                                if (lineBuf.length() < 120) {
                                    lineBuf.append(c);
                                } else {
                                    lineBuf.setLength(0);
                                }
                            }
                        }
                    }
                } catch (Exception e) {
                    if (isConnected.get()) {
                        closeSerial();
                        notifyJsStatus("DISCONNECTED", "Conexao serial perdida");
                    }
                    break;
                }
            }
        }, "CanableReadThread");
        readThread.setPriority(Thread.MAX_PRIORITY);
        readThread.start();
    }

    private void handleIncomingSlcanLine(String line) {
        if (line.isEmpty()) return;

        if (line.startsWith("t") && line.length() >= 5) {
            String idHex = line.substring(1, 4).toUpperCase();
            long now = System.currentTimeMillis();

            // Respostas de diagnóstico OBD-II / UDS passam sem latência
            if (idHex.startsWith("7")) {
                dispatchFrameToJs(line);
                return;
            }

            // Frame 0x422 (Demanda de Aceleração do Pedal): throttle de 80ms (~12.5 Hz)
            if ("422".equals(idHex)) {
                Long last = lastBroadcastSentMs.get("422");
                if (last == null || (now - last) >= 80) {
                    lastBroadcastSentMs.put("422", now);
                    dispatchFrameToJs(line);
                }
                return;
            }

            // Frame 0x430 (Boia Real do Tanque): throttle de 200ms (5 Hz)
            if ("430".equals(idHex)) {
                Long last = lastBroadcastSentMs.get("430");
                if (last == null || (now - last) >= 200) {
                    lastBroadcastSentMs.put("430", now);
                    dispatchFrameToJs(line);
                }
                return;
            }

            if (snifferMode.get()) {
                Long last = lastBroadcastSentMs.get(idHex);
                if (last == null || (now - last) >= 120) {
                    lastBroadcastSentMs.put(idHex, now);
                    dispatchFrameToJs(line);
                }
            }
        } else {
            dispatchFrameToJs(line);
        }
    }

    private void dispatchFrameToJs(final String line) {
        final String safeLine = line.replace("\\", "\\\\").replace("'", "\\'");
        mainHandler.post(() -> {
            if (webView != null) {
                webView.evaluateJavascript("if(window.onNativeSlcanFrame) window.onNativeSlcanFrame('" + safeLine + "');", null);
            }
        });
    }

    private void notifyJsStatus(final String state, final String message) {
        final String safeMsg = (message != null ? message : "").replace("\\", "\\\\").replace("'", "\\'");
        mainHandler.post(() -> {
            if (webView != null) {
                webView.evaluateJavascript(
                        "if(window.onNativeUsbStatus) window.onNativeUsbStatus('" + state + "', '" + safeMsg + "');",
                        null
                );
            }
        });
    }

    private synchronized boolean writeRaw(String data) {
        if (!isConnected.get() || usbConnection == null || epOut == null) return false;
        try {
            byte[] bytes = data.getBytes(StandardCharsets.US_ASCII);
            int res = usbConnection.bulkTransfer(epOut, bytes, bytes.length, 150);
            return res >= 0;
        } catch (Exception e) {
            return false;
        }
    }

    private synchronized void closeSerial() {
        isConnected.set(false);
        if (usbConnection != null && epOut != null) {
            try {
                byte[] closeCmd = "C\r".getBytes(StandardCharsets.US_ASCII);
                usbConnection.bulkTransfer(epOut, closeCmd, closeCmd.length, 50);
            } catch (Exception ignored) {}
        }
        if (usbConnection != null) {
            try {
                usbConnection.close();
            } catch (Exception ignored) {}
            usbConnection = null;
        }
        epIn = null;
        epOut = null;
    }

    public class AndroidUsbBridge {

        @JavascriptInterface
        public void connect() {
            scanAndConnectUsb();
        }

        @JavascriptInterface
        public void disconnect() {
            closeSerial();
            notifyJsStatus("DISCONNECTED", "Desconectado manualmente");
        }

        @JavascriptInterface
        public boolean isConnected() {
            return isConnected.get();
        }

        @JavascriptInterface
        public boolean sendCommand(String cmd) {
            if (cmd == null) return false;
            String formatted = cmd.endsWith("\r") ? cmd : (cmd + "\r");
            return writeRaw(formatted);
        }

        @JavascriptInterface
        public void setSnifferMode(boolean enabled) {
            snifferMode.set(enabled);
        }

        @JavascriptInterface
        public void startGps() {
            mainHandler.post(() -> startGpsInternal());
        }

        @JavascriptInterface
        public void stopGps() {
            mainHandler.post(() -> stopGpsInternal());
        }

        @JavascriptInterface
        public boolean isGpsActive() {
            return isGpsTracking.get();
        }

        @JavascriptInterface
        public void toggleFullscreen(boolean fullscreen) {
            mainHandler.post(() -> {
                View decorView = getWindow().getDecorView();
                if (fullscreen) {
                    decorView.setSystemUiVisibility(
                            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    );
                } else {
                    decorView.setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
                }
            });
        }

        @JavascriptInterface
        public String saveAndShareCsv(String filename, String csvContent) {
            try {
                String cleanName = (filename != null && !filename.isEmpty()) ? filename : "viagem_fiesta.csv";
                if (!cleanName.endsWith(".csv")) cleanName += ".csv";

                if (Build.VERSION.SDK_INT >= 29) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.Downloads.DISPLAY_NAME, cleanName);
                    values.put(MediaStore.Downloads.MIME_TYPE, "text/csv");
                    values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);

                    Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (uri != null) {
                        try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                            if (os != null) {
                                os.write(csvContent.getBytes(StandardCharsets.UTF_8));
                            }
                        }
                        final String savedName = cleanName;
                        mainHandler.post(() -> Toast.makeText(
                                MainActivity.this,
                                "Salvo em Downloads: " + savedName,
                                Toast.LENGTH_LONG
                        ).show());

                        Intent shareIntent = new Intent(Intent.ACTION_SEND);
                        shareIntent.setType("text/csv");
                        shareIntent.putExtra(Intent.EXTRA_STREAM, uri);
                        shareIntent.setClipData(android.content.ClipData.newRawUri("CSV", uri));
                        shareIntent.putExtra(Intent.EXTRA_SUBJECT, cleanName);
                        shareIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(shareIntent, "Compartilhar Log CSV"));
                        return "SAVED:" + cleanName;
                    }
                }

                Intent sendIntent = new Intent(Intent.ACTION_SEND);
                sendIntent.setType("text/plain");
                sendIntent.putExtra(Intent.EXTRA_SUBJECT, cleanName);
                sendIntent.putExtra(Intent.EXTRA_TEXT, csvContent);
                startActivity(Intent.createChooser(sendIntent, "Exportar Log CSV"));
                return "SHARED:" + cleanName;
            } catch (Exception e) {
                return "ERROR:" + e.getMessage();
            }
        }
    }
}
