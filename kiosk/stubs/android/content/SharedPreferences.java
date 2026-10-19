// Compile-only stub: never packaged. The real class comes from the device framework.
package android.content;
public interface SharedPreferences {
    int getInt(String key,int fallback);
    String getString(String key, String defValue);
    Editor edit();
    interface Editor {
        Editor putInt(String key,int value);
        Editor putString(String key, String value);
        void apply();
    }
}
