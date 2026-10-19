package com.homehub.kiosk;
/** Matches the dashboard's centered 1280x800 stage and 232px sidebar. */
public final class PanelBounds {
 public static int[] at(int width,int height) {
  float scale=Math.min(width/1280f,height/800f);
  int left=Math.round((width-1280*scale)/2+232*scale);
  int top=Math.round((height-800*scale)/2);
  return new int[]{left,top,Math.round(1048*scale),Math.round(800*scale)};
 }
 public static int brightness(String value) {
  int number=Integer.parseInt(value);
  if(number<10 || number>100)throw new IllegalArgumentException();
  return number;
 }
}
