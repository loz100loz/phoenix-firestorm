integer is_open;

default
{
    touch_start(integer count)
    {
        is_open = !is_open;
        if (is_open)
        {
            llOwnerSay("Fake door open");
        }
        else
        {
            llOwnerSay("Fake door closed");
        }
    }
}
