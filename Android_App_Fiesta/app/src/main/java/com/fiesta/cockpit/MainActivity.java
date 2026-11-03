package com.fiesta.cockpit;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
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

import androidx.appcompat.app.AppCompatActivity;

import com.hoho.android.usbserial.driver.CdcAcmSerialDriver;
import com.hoho.android.usbserial.driver.ProbeTable;
import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;

import org.json.JSONObject;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public class MainActivity extends AppCompatActivity {

    private static final String ACTION_USB_PERMISSION = "com.fiesta.cockpit.USB_PERMISSION";

    private WebView webView;
    private UsbManager usbManager;
    private UsbSerialPort usbSerialPort;
    private UsbDeviceConnection usbConnection;
    private final AtomicBoolean isConnected = new AtomicBoolean(false);
    private final AtomicBoolean snifferMode = new AtomicBoolean(false);
    private Thread readThread;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    // Throttling por ID CAN para evitar sobrecarga de 500 frames/s na WebView
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
                    notifyJsStatus("PERMISSION_DENIED", "Permissão USB negada pelo usuário.");
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

        // Mantém a tela sempre acesa durante a condução no Fiesta
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                // Tenta conectar automaticamente 600ms após carregar a interface
                mainHandler.postDelayed(() -> scanAndConnectUsb(), 600);
            }
        });

        webView.addJavascriptInterface(new AndroidUsbBridge(), "AndroidUSB");
        webView.loadUrl("file:///android_asset/index.html");

        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_USB_PERMISSION);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(usbReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(usbReceiver, filter);
        }
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
        closeSerial();
        try {
            unregisterReceiver(usbReceiver);
        } catch (Exception ignored) {}
        super.onDestroy();
    }

    private UsbSerialProber getCustomProber() {
        ProbeTable customTable = new ProbeTable();
        // CANable V2.1 Oficial (Openlight Labs STM32G431): VID 0x16D0, PID 0x117E
        customTable.addProduct(0x16D0, 0x117E, CdcAcmSerialDriver.class);
        // CANable V1 (OpenMoko): VID 0x1D50, PID 0x606F
        customTable.addProduct(0x1D50, 0x606F, CdcAcmSerialDriver.class);
        // STMicroelectronics Virtual COM Port
        customTable.addProduct(0x0483, 0x5740, CdcAcmSerialDriver.class);
        return new UsbSerialProber(customTable);
    }

    private synchronized void scanAndConnectUsb() {
        if (isConnected.get()) {
            notifyJsStatus("CONNECTED", "CANable V2.1 Ativa (500 kbps)");
            return;
        }

        if (usbManager == null) {
            notifyJsStatus("ERROR", "UsbManager indisponível no Android");
            return;
        }

        HashMap<String, UsbDevice> deviceList = usbManager.getDeviceList();
        if (deviceList == null || deviceList.isEmpty()) {
            notifyJsStatus("DISCONNECTED", "Nenhum dispositivo USB detectado no cabo OTG");
            return;
        }

        // Procura primeiro com o prober padrão + customizado (16D0:117E)
        List<UsbSerialDriver> drivers = UsbSerialProber.getDefaultProber().findAllDrivers(usbManager);
        if (drivers.isEmpty()) {
            drivers = getCustomProber().findAllDrivers(usbManager);
        }

        UsbDevice targetDevice = null;
        if (!drivers.isEmpty()) {
            targetDevice = drivers.get(0).getDevice();
        } else {
            // Fallback universal: usa o primeiro dispositivo USB conectado como CDC-ACM
            targetDevice = deviceList.values().iterator().next();
        }

        if (targetDevice != null) {
            if (usbManager.hasPermission(targetDevice)) {
                openDevice(targetDevice);
            } else {
                notifyJsStatus("REQUESTING_PERMISSION", "Solicitando permissão USB ao Android...");
                Intent permIntent = new Intent(ACTION_USB_PERMISSION);
                permIntent.setPackage(getPackageName());
                int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
                        ? PendingIntent.FLAG_MUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
                        : PendingIntent.FLAG_UPDATE_CURRENT;
                PendingIntent pi = PendingIntent.getBroadcast(this, 0, permIntent, flags);
                usbManager.requestPermission(targetDevice, pi);
            }
        }
    }

    private synchronized void openDevice(UsbDevice device) {
        closeSerial();

        try {
            UsbSerialDriver driver = UsbSerialProber.getDefaultProber().probeDevice(device);
            if (driver == null) {
                driver = getCustomProber().probeDevice(device);
            }
            if (driver == null) {
                driver = new CdcAcmSerialDriver(device);
            }

            if (driver.getPorts().isEmpty()) {
                notifyJsStatus("ERROR", "Nenhuma porta CDC encontrada no dispositivo");
                return;
            }

            UsbDeviceConnection conn = usbManager.openDevice(device);
            if (conn == null) {
                notifyJsStatus("ERROR", "Falha ao abrir conexão USB nativa");
                return;
            }

            UsbSerialPort port = driver.getPorts().get(0);
            port.open(conn);
            port.setParameters(115200, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE);
            try {
                port.setDTR(true);
                port.setRTS(true);
            } catch (Exception ignored) {}

            this.usbConnection = conn;
            this.usbSerialPort = port;
            this.isConnected.set(true);

            String devInfo = String.format("CANable %04X:%04X (500k)", device.getVendorId(), device.getProductId());
            notifyJsStatus("CONNECTED", devInfo);

            // Inicializa automaticamente o protocolo SLCAN em 500 kbps (Ford HS-CAN)
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
            byte[] buffer = new byte[1024];
            StringBuilder lineBuf = new StringBuilder(128);

            while (isConnected.get() && usbSerialPort != null) {
                try {
                    int len = usbSerialPort.read(buffer, 40);
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
                        notifyJsStatus("DISCONNECTED", "Conexão serial perdida");
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

        // Quadros CAN standard 11-bit: tIIILDD...
        if (line.startsWith("t") && line.length() >= 5) {
            String idHex = line.substring(1, 4).toUpperCase();
            long now = System.currentTimeMillis();

            // Respostas de diagnóstico OBD-II / UDS (0x7E8, 0x728, 0x72E) passam com prioridade imediata!
            if (idHex.startsWith("7")) {
                dispatchFrameToJs(line);
                return;
            }

            // Frame 0x422 (Torque Real + Ar-Condicionado): throttle de 80ms (~12.5 Hz)
            if ("422".equals(idHex)) {
                Long last = lastBroadcastSentMs.get("422");
                if (last == null || (now - last) >= 80) {
                    lastBroadcastSentMs.put("422", now);
                    dispatchFrameToJs(line);
                }
                return;
            }

            // Frame 0x430 (Boia Real do Tanque + Botão A/C): throttle de 200ms (5 Hz)
            if ("430".equals(idHex)) {
                Long last = lastBroadcastSentMs.get("430");
                if (last == null || (now - last) >= 200) {
                    lastBroadcastSentMs.put("430", now);
                    dispatchFrameToJs(line);
                }
                return;
            }

            // Se o usuário estiver na aba Sniffer / Monitor Bruto, encaminha os demais IDs com throttle de 120ms
            if (snifferMode.get()) {
                Long last = lastBroadcastSentMs.get(idHex);
                if (last == null || (now - last) >= 120) {
                    lastBroadcastSentMs.put(idHex, now);
                    dispatchFrameToJs(line);
                }
            }
        } else {
            // Respostas de comando (ex: 'V' versão do firmware)
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
        if (!isConnected.get() || usbSerialPort == null) return false;
        try {
            usbSerialPort.write(data.getBytes(StandardCharsets.US_ASCII), 150);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    private synchronized void closeSerial() {
        isConnected.set(false);
        if (usbSerialPort != null) {
            try {
                usbSerialPort.write("C\r".getBytes(StandardCharsets.US_ASCII), 50);
            } catch (Exception ignored) {}
            try {
                usbSerialPort.close();
            } catch (Exception ignored) {}
            usbSerialPort = null;
        }
        if (usbConnection != null) {
            try {
                usbConnection.close();
            } catch (Exception ignored) {}
            usbConnection = null;
        }
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

                // Salva na pasta pública Downloads do Android (Android 10+ MediaStore)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
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
                        mainHandler.post(() -> Toast.makeText(
                                MainActivity.this,
                                "Salvo em Downloads: " + cleanName,
                                Toast.LENGTH_LONG
                        ).show());

                        // Abre menu de compartilhamento do Android (WhatsApp / Drive)
                        Intent shareIntent = new Intent(Intent.ACTION_SEND);
                        shareIntent.setType("text/csv");
                        shareIntent.putExtra(Intent.EXTRA_STREAM, uri);
                        shareIntent.putExtra(Intent.EXTRA_SUBJECT, cleanName);
                        shareIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(shareIntent, "Compartilhar Log CSV"));
                        return "SAVED:" + cleanName;
                    }
                }

                // Fallback de compartilhamento de texto direto
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
