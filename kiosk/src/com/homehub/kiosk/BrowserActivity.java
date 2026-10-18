package com.homehub.kiosk;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.view.View;
import android.view.KeyEvent;
import android.widget.LinearLayout;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.webkit.CookieManager;
import android.graphics.Bitmap;

/** One transient public-web tab; no JS/native bridge, downloads or new permissions. */
public class BrowserActivity extends Activity {
    private WebView web;
    private EditText address;
    private TextView status;
    private Button back, forward, reload;
    private boolean loading;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setSoftInputMode(3); // initially hide keyboard
        getWindow().addFlags(0x00000080); // keep screen on while cooking/browsing
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(1);
        root.setBackgroundColor(0xFFFBFAF7);
        LinearLayout entry = new LinearLayout(this);
        address = new EditText(this);
        address.setSingleLine(true);
        address.setSelectAllOnFocus(true);
        address.setTextSize(19);
        address.setHint("Search or enter https://…");
        address.setInputType(1 | 16); // text URI
        address.setImeOptions(2); // Go
        address.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override public boolean onEditorAction(TextView v, int id, KeyEvent event) { loadInput(); return true; }
        });
        entry.addView(address, new LinearLayout.LayoutParams(0,64,1));
        Button go=new Button(this);go.setText("Go");
        go.setOnClickListener(new View.OnClickListener() { public void onClick(View v) { loadInput(); } });
        entry.addView(go,new LinearLayout.LayoutParams(120,-1));
        root.addView(entry,new LinearLayout.LayoutParams(-1,64));
        LinearLayout tools = new LinearLayout(this);
        addButton(tools,"Dashboard",new View.OnClickListener() { public void onClick(View v) { finish(); } });
        back = addButton(tools,"Back",new View.OnClickListener() { public void onClick(View v) { if(web.canGoBack())web.goBack(); } });
        forward = addButton(tools,"Forward",new View.OnClickListener() { public void onClick(View v) { if(web.canGoForward())web.goForward(); } });
        reload=addButton(tools,"Reload",new View.OnClickListener() { public void onClick(View v) {
            if(loading){web.stopLoading();loading=false;reload.setText("Reload");status.setText("Stopped. You can read this page or enter another address.");}
            else web.reload();
        } });
        addButton(tools,"Read recipe",new View.OnClickListener() { public void onClick(View v) { readRecipe(); } });
        root.addView(tools,new LinearLayout.LayoutParams(-1,60));
        status = new TextView(this);
        status.setTextSize(15);
        status.setText("Open a recipe page, then tap Read recipe.");
        root.addView(status,new LinearLayout.LayoutParams(-1,28));
        web = new WebView(this);
        WebSettings settings=web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(1); // MIXED_CONTENT_NEVER_ALLOW
        settings.setCacheMode(2); // LOAD_NO_CACHE
        settings.setSaveFormData(false);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient() {
            @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView view,String target) {
                if (BrowserPolicy.isPublicHttps(target)) return null;
                return new android.webkit.WebResourceResponse("text/plain","UTF-8",
                        new java.io.ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,String target) {
                if (!BrowserPolicy.isPublicHttps(target)) {
                    status.setText("Only HTTPS website addresses can open here.");
                    return true;
                }
                return false;
            }
            @Override public void onPageStarted(WebView view,String target,Bitmap icon) {
                loading=true;reload.setText("Stop");address.setText(target);status.setText("Loading…");
            }
            @Override public void onPageFinished(WebView view,String target) {
                loading=false;reload.setText("Reload");address.setText(target);web.requestFocus();
                back.setEnabled(view.canGoBack());forward.setEnabled(view.canGoForward());
                status.setText("Open a recipe page, then tap Read recipe.");
            }
            @Override public void onReceivedError(WebView view,int code,String description,String target) {
                loading=false;reload.setText("Reload");status.setText("Page unavailable. Search again, or return to Dashboard.");
            }
        });
        root.addView(web,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root);
        address.setText(getIntent().getStringExtra("query"));
        loadInput();
    }

    private Button addButton(LinearLayout row,String label,View.OnClickListener action) {
        Button button=new Button(this);button.setText(label);button.setTextSize(17);button.setOnClickListener(action);
        row.addView(button,new LinearLayout.LayoutParams(0,-1,1));return button;
    }
    private void loadInput() {
        try {
            String target=BrowserPolicy.destination(((TextView)address).getText().toString());
            android.view.inputmethod.InputMethodManager keyboard=(android.view.inputmethod.InputMethodManager)getSystemService("input_method");
            if(keyboard!=null)keyboard.hideSoftInputFromWindow(address.getWindowToken(),0);
            web.loadUrl(target);
        }
        catch (IllegalArgumentException ignored) { status.setText("Enter search words or an HTTPS website address."); }
    }
    private void readRecipe() {
        String target=web.getUrl();
        if(!BrowserPolicy.isPublicHttps(target)) { status.setText("Open an HTTPS recipe page first.");return; }
        setResult(-1,new Intent().putExtra("recipe",target));finish();
    }
    @Override public void onBackPressed() { if(web.canGoBack())web.goBack();else finish(); }
    @Override protected void onPause() { web.onPause();super.onPause(); }
    @Override protected void onResume() { super.onResume();if(web!=null)web.onResume(); }
    @Override protected void onDestroy() { if(web!=null){web.stopLoading();web.clearHistory();web.destroy();}super.onDestroy(); }
}
