package com.homehub.kiosk;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.view.MotionEvent;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/**
 * Fullscreen dashboard kiosk. Loads the Home Hub page, keeps the screen on, hides system bars,
 * and retries every few seconds while the server is unreachable. A three-finger hold for two
 * seconds exits (the dashboard itself uses a two-finger hold for its admin panel).
 *
 * Optional: `am start -n com.homehub.kiosk/.MainActivity --es url http://127.0.0.1:8100/`.
 */
public class MainActivity extends Activity {
    private static final String DEFAULT_URL = "http://127.0.0.1:8099/";
    private static final long RETRY_MS = 5000;
    private static final long EXIT_HOLD_MS = 2000;

    // Platform constants (API 23), written out because this app compiles against minimal stubs.
    private static final int FLAG_KEEP_SCREEN_ON = 0x00000080;
    private static final int FLAG_FULLSCREEN = 0x00000400;
    private static final int IMMERSIVE_FLAGS =
            0x00000002   // SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | 0x00000004 // SYSTEM_UI_FLAG_FULLSCREEN
            | 0x00000100 // SYSTEM_UI_FLAG_LAYOUT_STABLE
            | 0x00000200 // SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | 0x00000400 // SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | 0x00001000; // SYSTEM_UI_FLAG_IMMERSIVE_STICKY
    private static final int ACTION_UP = 1;
    private static final int ACTION_CANCEL = 3;
    private static final int ACTION_POINTER_DOWN = 5;
    private static final int ACTION_POINTER_UP = 6;

    private final Handler handler = new Handler();
    private WebView web;
    private String url = DEFAULT_URL;
    private boolean retryPending;

    private final Runnable retry = new Runnable() {
        @Override
        public void run() {
            retryPending = false;
            web.loadUrl(url);
        }
    };

    private final Runnable exit = new Runnable() {
        @Override
        public void run() {
            finish();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(FLAG_KEEP_SCREEN_ON | FLAG_FULLSCREEN);

        String requested = getIntent().getStringExtra("url");
        if (requested != null && (requested.startsWith("http://") || requested.startsWith("https://"))) {
            url = requested;
        }

        WebView.setWebContentsDebuggingEnabled(true); // reachable only over ADB
        web = new WebView(this);
        web.setBackgroundColor(0xFF000000);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setTextZoom(100);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String target) {
                return false;
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                view.loadData("<body style=\"background:#000;color:#999;font:28px sans-serif;"
                        + "display:flex;align-items:center;justify-content:center;height:100vh;margin:0\">"
                        + "Waiting for Home Hub…</body>", "text/html", "utf-8");
                if (!retryPending) {
                    retryPending = true;
                    handler.postDelayed(retry, RETRY_MS);
                }
            }
        });
        setContentView(web);
        web.loadUrl(url);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        hideSystemBars();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(retry);
        handler.removeCallbacks(exit);
        web.destroy();
        super.onDestroy();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        if (action == ACTION_POINTER_DOWN && event.getPointerCount() == 3) {
            handler.postDelayed(exit, EXIT_HOLD_MS);
        } else if (action == ACTION_POINTER_DOWN || action == ACTION_POINTER_UP
                || action == ACTION_UP || action == ACTION_CANCEL) {
            handler.removeCallbacks(exit);
        }
        return super.dispatchTouchEvent(event);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        }
    }

    private void hideSystemBars() {
        getWindow().getDecorView().setSystemUiVisibility(IMMERSIVE_FLAGS);
    }
}
