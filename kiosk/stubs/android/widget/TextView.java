package android.widget;
import android.view.View;
import android.content.Context;
public class TextView extends View {
 public TextView(Context context) { throw new RuntimeException(); }
 public void setText(CharSequence text) { throw new RuntimeException(); }
 public CharSequence getText() { throw new RuntimeException(); }
 public void setTextColor(int color){throw new RuntimeException();}
 public void setHintTextColor(int color){throw new RuntimeException();}
 public void setTextSize(float size) { throw new RuntimeException(); }
 public void setHint(CharSequence hint) { throw new RuntimeException(); }
 public void setSelectAllOnFocus(boolean select) { throw new RuntimeException(); }
 public void setSingleLine(boolean single) { throw new RuntimeException(); }
 public void setInputType(int type) { throw new RuntimeException(); }
 public void setImeOptions(int options) { throw new RuntimeException(); }
 public void setOnEditorActionListener(OnEditorActionListener listener) { throw new RuntimeException(); }
 public interface OnEditorActionListener { boolean onEditorAction(TextView view,int action,android.view.KeyEvent event); }
}
