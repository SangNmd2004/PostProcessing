connect -url tcp:127.0.0.1:3121
puts "ZC702_TARGET_LIST_BEGIN"
puts [targets]
puts "ZC702_TARGET_PROPERTIES_BEGIN"
puts [targets -target-properties]
puts "ZC702_TARGET_LIST_END"
