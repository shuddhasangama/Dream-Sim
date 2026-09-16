#import <Capacitor/Capacitor.h>

// Plugin name string must stay exactly "SessionVault" — it's what
// registerPlugin('SessionVault') in src/main.js binds to, matching the
// @CapacitorPlugin(name = "SessionVault") on the Android side.
CAP_PLUGIN(SessionVaultPlugin, "SessionVault",
    CAP_PLUGIN_METHOD(read, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(write, CAPPluginReturnPromise);
    CAP_PLUGIN_METHOD(clear, CAPPluginReturnPromise);
)
