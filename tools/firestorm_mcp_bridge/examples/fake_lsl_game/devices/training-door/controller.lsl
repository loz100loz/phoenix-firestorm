integer is_open;

default
{
    touch_start(integer count)
    {
        is_open = !is_open;
        llOwnerSay(is_open ? "Fake door open" : "Fake door closed");
    }
}
