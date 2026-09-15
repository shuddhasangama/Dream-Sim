package com.dhashu.app;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(android.os.Bundle state) {
        registerPlugin(SessionVault.class);
        super.onCreate(state);
        getWindow().setFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE,
            android.view.WindowManager.LayoutParams.FLAG_SECURE);
    }
}
