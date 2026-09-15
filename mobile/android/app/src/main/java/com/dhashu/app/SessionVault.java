package com.dhashu.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Only the rotating refresh credential is persisted; no OTP or profile data. */
@CapacitorPlugin(name = "SessionVault")
public class SessionVault extends Plugin {
    private static final String ALIAS = "dhashu.session.v1";
    private SharedPreferences prefs() { return getContext().getSharedPreferences(ALIAS, Context.MODE_PRIVATE); }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias(ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey) store.getKey(ALIAS, null);
    }
    @PluginMethod public synchronized void write(PluginCall call) {
        String value = call.getString("value");
        if (value == null || value.length() < 32 || value.length() > 128) { call.reject("Invalid credential."); return; }
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
            String encrypted = Base64.encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
            String iv = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP);
            if (!prefs().edit().putString("encrypted", encrypted).putString("iv", iv).commit()) throw new Exception();
            call.resolve();
        } catch (Exception e) { call.reject("Secure storage unavailable."); }
    }
    @PluginMethod public synchronized void read(PluginCall call) {
        String encrypted = prefs().getString("encrypted", null);
        if (encrypted == null) { JSObject result = new JSObject(); result.put("value", JSObject.NULL); call.resolve(result); return; }
        try {
            byte[] iv = Base64.decode(prefs().getString("iv", ""), Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            String value = new String(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)), StandardCharsets.UTF_8);
            JSObject result = new JSObject(); result.put("value", value); call.resolve(result);
        } catch (Exception e) {
            prefs().edit().clear().commit(); call.reject("Stored session is unavailable. Sign in again.");
        }
    }
    @PluginMethod public synchronized void clear(PluginCall call) {
        if (prefs().edit().clear().commit()) call.resolve(); else call.reject("Could not clear secure storage.");
    }
}
