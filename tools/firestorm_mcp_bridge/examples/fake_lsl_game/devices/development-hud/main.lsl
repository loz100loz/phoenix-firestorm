integer touches;

default
{
    touch_start(integer count)
    {
        touches += count;
        llOwnerSay("Fake HUD touch " + (string)touches);
    }
}
